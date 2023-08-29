"""
websocket functions
"""
from __future__ import annotations

import platform
import shutil
import sys
from contextlib import contextmanager
from threading import Event
from typing import Any, Generator
from uuid import uuid4

from opsicommon.client.opsiservice import MessagebusListener
from opsicommon.logging import get_logger  # type: ignore[import]
from opsicommon.messagebus import (
	ChannelSubscriptionEventMessage,
	ChannelSubscriptionRequestMessage,
	JSONRPCRequestMessage,
	JSONRPCResponseMessage,
	Message,
	TerminalCloseEventMessage,
	TerminalDataReadMessage,
	TerminalDataWriteMessage,
	TerminalOpenEventMessage,
	TerminalOpenRequestMessage,
)

from opsicli.opsiservice import get_service_connection
from opsicli.utils import stream_wrap

if platform.system().lower() == "windows":
	import msvcrt  # pylint: disable=import-error

CHANNEL_SUB_TIMEOUT = 5
JSONRPC_TIMEOUT = 10

logger = get_logger("opsicli")


def log_message(message: Message) -> None:
	logger.info("Got message of type %s", message.type)
	debug_string = ""
	for key, value in message.to_dict().items():
		debug_string += f"\t{key}: {value}\n"
	logger.debug(debug_string)
	# logger.devel(debug_string)  # for test_messagebus.py


class MessagebusConnection(MessagebusListener):  # pylint: disable=too-many-instance-attributes
	terminal_id: str

	def __init__(self) -> None:
		MessagebusListener.__init__(self)
		self.channel_subscription_locks: dict[str, Event] = {}
		self.subscribed_channels: list[str] = []
		self.initial_subscription_event = Event()
		self.jsonrpc_response_event = Event()
		self.jsonrpc_response: Any | None = None
		self.service_client = get_service_connection()

	def message_received(self, message: Message) -> None:
		log_message(message)
		try:
			callback_name = f"_on_{message.type}"
			if hasattr(self, callback_name):
				callback = getattr(self, callback_name)
				callback(message)
			else:
				logger.debug("No available callback for event of message %r", message.type)
		except Exception as err:  # pylint: disable=broad-except
			logger.error(err, exc_info=True)

	def _on_channel_subscription_event(self, message: ChannelSubscriptionEventMessage) -> None:
		self.subscribed_channels = message.subscribed_channels
		for channel in message.subscribed_channels:
			if channel in self.channel_subscription_locks:
				self.channel_subscription_locks[channel].set()
			else:
				self.initial_subscription_event.set()

	def _on_jsonrpc_response(self, message: JSONRPCResponseMessage) -> None:
		logger.notice("Received jsonrpc response message")
		self.jsonrpc_response = message.error if message.error else message.result
		self.jsonrpc_response_event.set()

	def subscribe_to_channel(self, channel: str) -> None:
		if channel in self.subscribed_channels:
			return
		try:
			self.channel_subscription_locks[channel] = Event()
			csr = ChannelSubscriptionRequestMessage(sender="@", operation="add", channels=[channel], channel="service:messagebus")
			logger.notice("Requesting access to channel %r", channel)
			log_message(csr)
			self.service_client.messagebus.send_message(csr)
			if not self.channel_subscription_locks[channel].wait(CHANNEL_SUB_TIMEOUT):
				raise ConnectionError(f"Could not subscribe to channel {channel}")
		finally:
			del self.channel_subscription_locks[channel]

	@contextmanager
	def connection(self) -> Generator[MessagebusConnection, None, None]:
		try:
			if not self.service_client.messagebus_connected:
				logger.debug("Connecting to messagebus.")
				self.service_client.connect_messagebus()
			with self.register(self.service_client.messagebus):
				if not self.initial_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
					raise ConnectionError("Failed to subscribe to session channel.")
				yield self
		finally:
			if self.service_client.messagebus_connected:
				logger.debug("Disconnecting from messagebus.")
				self.service_client.disconnect_messagebus()

	def jsonrpc(self, channel: str, method: str, params: tuple | None = None) -> Any:
		message = JSONRPCRequestMessage(
			method=method,
			params=params or (),
			api_version="2.0",
			sender="@",
			channel=channel,
		)
		self.service_client.messagebus.send_message(message)
		logger.notice("Sending jsonrpc-request, awaiting response...")
		if not self.jsonrpc_response and not self.jsonrpc_response_event.wait(JSONRPC_TIMEOUT):
			raise TimeoutError("Timed out waiting for jsonrpc response.")
		self.jsonrpc_response_event.clear()
		if not self.jsonrpc_response:
			raise ConnectionError("Failed to receive jsonrpc response.")
		result = self.jsonrpc_response
		self.jsonrpc_response = None
		return result


class TerminalMessagebusConnection(MessagebusConnection):
	terminal_id: str

	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self.should_close = False
		self.terminal_write_channel: str | None = None
		self.terminal_open_event = Event()

	def _on_terminal_open_event(self, message: TerminalOpenEventMessage) -> None:
		if message.terminal_id == self.terminal_id:
			self.terminal_write_channel = message.back_channel
			self.terminal_open_event.set()

	def _on_terminal_data_read(self, message: TerminalDataReadMessage) -> None:
		if message.terminal_id == self.terminal_id:
			sys.stdout.buffer.write(message.data)
			sys.stdout.flush()  # This actually pops the buffer to terminal (without waiting for '\n')

	def _on_terminal_close_event(self, message: TerminalCloseEventMessage) -> None:
		if message.terminal_id == self.terminal_id:
			logger.notice("received terminal close event - shutting down")
			sys.stdout.buffer.write(b"\nreceived terminal close event - press Enter to return to local shell")
			sys.stdout.flush()  # This actually pops the buffer to terminal (without waiting for '\n')
			self.should_close = True

	def transmit_input(self, term_write_channel: str, data: bytes | None = None) -> None:
		if not self.terminal_id:
			raise ValueError("Terminal id not set.")
		if data:
			tdw = TerminalDataWriteMessage(sender="@", channel=term_write_channel, terminal_id=self.terminal_id, data=data)
			log_message(tdw)
			self.service_client.messagebus.send_message(tdw)
			return
		# If no data is given, transmit from stdin until EOF
		while not self.should_close:
			if platform.system().lower() == "windows":
				data = msvcrt.getch()  # type: ignore
			else:
				data = sys.stdin.read(1).encode("utf-8")
			if not data:  # or data == b"\x03":  # Ctrl+C
				self.should_close = True
				break
			self.transmit_input(term_write_channel, data)

	def open_new_terminal(self, term_request_channel: str) -> None:
		self.subscribe_to_channel(f"session:{self.terminal_id}")
		size = shutil.get_terminal_size()
		tor = TerminalOpenRequestMessage(
			sender="@",
			channel=term_request_channel,
			terminal_id=self.terminal_id,
			back_channel=f"session:{self.terminal_id}",
			rows=size.lines,
			cols=size.columns,
		)
		logger.notice("Requesting to open terminal with id %s ", self.terminal_id)
		log_message(tor)
		self.service_client.messagebus.send_message(tor)

	def get_terminal_channel_pair(self, target: str) -> tuple[str, str]:
		term_read_channel = f"session:{self.terminal_id}"
		self.subscribe_to_channel(term_read_channel)

		if target.lower() == "configserver":
			term_request_channel = "service:config:terminal"
		else:
			term_request_channel = f"host:{target}"

		self.open_new_terminal(term_request_channel)
		if not self.terminal_open_event.wait(CHANNEL_SUB_TIMEOUT) or self.terminal_write_channel is None:
			raise ConnectionError("Could not open new terminal")
		self.terminal_open_event.clear()  # prepare for catching the next terminal_open_event

		return (term_read_channel, self.terminal_write_channel)

	def run_terminal(self, target: str, term_id: str | None = None) -> None:
		if term_id:
			self.terminal_id = term_id
		else:
			self.terminal_id = str(uuid4())
		with self.connection():
			(_, term_write_channel) = self.get_terminal_channel_pair(target)
			logger.notice("Return to local shell with 'exit' or 'Ctrl+D'")
			with stream_wrap():
				self.transmit_input(term_write_channel)
