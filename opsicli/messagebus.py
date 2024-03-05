"""
websocket functions
"""
from __future__ import annotations

import platform
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime
from threading import Event
from typing import Any, Generator
from uuid import uuid4

from opsicommon.client.opsiservice import MessagebusListener
from opsicommon.logging import get_logger  # type: ignore[import]
from opsicommon.messagebus import (
	CONNECTION_USER_CHANNEL,
	ChannelSubscriptionEventMessage,
	ChannelSubscriptionRequestMessage,
	JSONRPCRequestMessage,
	JSONRPCResponseMessage,
	Message,
	ProcessDataReadMessage,
	ProcessErrorMessage,
	ProcessMessage,
	ProcessStartEventMessage,
	ProcessStartRequestMessage,
	ProcessStopEventMessage,
	ProcessStopRequestMessage,
	TerminalCloseEventMessage,
	TerminalDataReadMessage,
	TerminalDataWriteMessage,
	TerminalErrorMessage,
	TerminalOpenEventMessage,
	TerminalOpenRequestMessage,
)

from opsicli.opsiservice import get_service_connection
from opsicli.utils import stream_wrap

if platform.system().lower() == "windows":
	import msvcrt

CHANNEL_SUB_TIMEOUT = 5.0
JSONRPC_TIMEOUT = 15.0
PROCESS_EXECUTE_TIMEOUT = 60.0

logger = get_logger("opsicli")


def log_message(message: Message) -> None:
	logger.info("Got message of type %s", message.type)
	debug_string = ""
	for key, value in message.to_dict().items():
		debug_string += f"\t{key}: {value}\n"
	logger.debug(debug_string)
	# logger.devel(debug_string)  # for test_messagebus.py


class MessagebusConnection(MessagebusListener):
	def __init__(self) -> None:
		MessagebusListener.__init__(self)
		self.channel_subscription_locks: dict[str, Event] = {}
		self.subscribed_channels: list[str] = []
		self.initial_subscription_event = Event()
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
		except Exception as err:
			logger.error(err, exc_info=True)

	def _on_channel_subscription_event(self, message: ChannelSubscriptionEventMessage) -> None:
		self.subscribed_channels = message.subscribed_channels
		for channel in message.subscribed_channels:
			if channel in self.channel_subscription_locks:
				self.channel_subscription_locks[channel].set()
			else:
				self.initial_subscription_event.set()

	def subscribe_to_channel(self, channel: str) -> None:
		if channel in self.subscribed_channels:
			return
		try:
			self.channel_subscription_locks[channel] = Event()
			csr = ChannelSubscriptionRequestMessage(
				sender=CONNECTION_USER_CHANNEL, operation="add", channels=[channel], channel="service:messagebus"
			)
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


class JSONRPCMessagebusConnection(MessagebusConnection):
	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self.jsonrpc_response_events: dict[str | int, Event] = {}
		self.jsonrpc_responses: dict[str | int, Any] = {}

	def _on_jsonrpc_response(self, message: JSONRPCResponseMessage) -> None:
		logger.notice("Received jsonrpc response message")
		self.jsonrpc_responses[message.rpc_id] = message.error if message.error else message.result
		self.jsonrpc_response_events[message.rpc_id].set()

	def jsonrpc(self, channels: list[str], method: str, params: tuple | None = None, timeout: float = JSONRPC_TIMEOUT) -> dict[str, Any]:
		results: dict[str, Any] = {}
		rpc_ids: dict[str, str | int] = {}
		for channel in channels:
			message = JSONRPCRequestMessage(
				method=method,
				params=params or (),
				api_version="2.0",
				sender=CONNECTION_USER_CHANNEL,
				channel=channel,
			)
			self.jsonrpc_response_events[message.rpc_id] = Event()
			rpc_ids[channel] = message.rpc_id
			self.service_client.messagebus.send_message(message)
		logger.notice("Sent jsonrpc-request, awaiting response...")
		for channel, rpc_id in rpc_ids.items():
			if not self.jsonrpc_response_events[rpc_id].wait(timeout):
				results[channel] = TimeoutError("Timed out waiting for jsonrpc response.")
			elif not self.jsonrpc_responses[rpc_id]:
				results[channel] = ConnectionError("Failed to receive jsonrpc response.")
			else:
				results[channel] = self.jsonrpc_responses[rpc_id]
			if rpc_id in self.jsonrpc_responses:
				del self.jsonrpc_responses[rpc_id]
			if rpc_id in self.jsonrpc_response_events:
				del self.jsonrpc_response_events[rpc_id]
		return results


class ProcessMessagebusConnection(MessagebusConnection):
	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self.process_stop_events: dict[str, Event] = {}
		self.captured_process_messages: dict[str, list[ProcessMessage]] = {}

	def _on_process_data_read(self, message: ProcessDataReadMessage) -> None:
		logger.debug("Received process data read message")
		self.captured_process_messages[message.process_id].append(message)

	def _on_process_stop_event(self, message: ProcessStopEventMessage) -> None:
		logger.debug("Received process stop event message")
		self.captured_process_messages[message.process_id].append(message)
		self.process_stop_events[message.process_id].set()

	def _on_process_start_event(self, message: ProcessStartEventMessage) -> None:
		logger.debug("Received process start event message")
		self.captured_process_messages[message.process_id].append(message)

	def _on_process_error(self, message: ProcessErrorMessage) -> None:
		logger.debug("Received process error message")
		self.captured_process_messages[message.process_id].append(message)
		self.process_stop_events[message.process_id].set()

	def execute_processes(
		self, channels: list[str], command: tuple[str], shell: bool = False, timeout: float | None = None, wait_for_ending: bool = True
	) -> dict[str, list[ProcessMessage | Exception]]:
		timeout = timeout or PROCESS_EXECUTE_TIMEOUT
		results: dict[str, list[ProcessMessage | Exception]] = {}
		process_ids: dict[str, str] = {}
		for channel in channels:
			message = ProcessStartRequestMessage(
				command=command,
				sender=CONNECTION_USER_CHANNEL,
				channel=channel,
				shell=shell,
			)
			self.process_stop_events[message.process_id] = Event()
			process_ids[channel] = message.process_id
			self.captured_process_messages[message.process_id] = []
			self.service_client.messagebus.send_message(message)
		start_time = datetime.now()
		logger.notice("Sent process start request")
		if not wait_for_ending:
			return {}
		logger.info("Awaiting responses...")
		for channel, process_id in process_ids.items():
			waiting_time = max(timeout - (datetime.now() - start_time).total_seconds(), 0)
			logger.debug("Waiting for %s seconds until stopping", waiting_time)
			if not self.process_stop_events[process_id].wait(waiting_time):
				logger.warning("Timeout reached, terminating process at channel %s", channel)
				self.service_client.messagebus.send_message(
					ProcessStopRequestMessage(process_id=message.process_id, sender=CONNECTION_USER_CHANNEL, channel=channel)
				)
				results[channel] = [TimeoutError("Timed out waiting for process to stop")]
			else:
				results[channel] = list(self.captured_process_messages[process_id])
			if process_id in self.captured_process_messages:
				del self.captured_process_messages[process_id]
			if process_id in self.process_stop_events:
				del self.process_stop_events[process_id]
		return results


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

	def _on_terminal_error(self, message: TerminalErrorMessage) -> None:
		if message.terminal_id == self.terminal_id:
			logger.notice("received terminal error event - shutting down")
			sys.stdout.buffer.write(b"\nreceived terminal error event - press Enter to return to local shell")
			sys.stdout.flush()  # This actually pops the buffer to terminal (without waiting for '\n')
			self.should_close = True

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
			tdw = TerminalDataWriteMessage(
				sender=CONNECTION_USER_CHANNEL, channel=term_write_channel, terminal_id=self.terminal_id, data=data
			)
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
			if not self.should_close:
				self.transmit_input(term_write_channel, data)

	def open_new_terminal(self, term_request_channel: str) -> None:
		self.subscribe_to_channel(f"session:{self.terminal_id}")
		size = shutil.get_terminal_size()
		tor = TerminalOpenRequestMessage(
			sender=CONNECTION_USER_CHANNEL,
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
