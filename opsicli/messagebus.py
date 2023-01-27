"""
websocket functions
"""

import platform
import shutil
import sys
from threading import Event
from typing import Optional
from uuid import uuid4

from opsicommon.client.opsiservice import MessagebusListener  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]
from opsicommon.messagebus import (  # type: ignore[import]
	ChannelSubscriptionEventMessage,
	ChannelSubscriptionRequestMessage,
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

logger = get_logger("opsicli")


def log_message(message: Message) -> None:
	logger.info("Got message of type %s", message.type)
	debug_string = ""
	for key, value in message.to_dict().items():
		debug_string += f"\t{key}: {value}\n"
	logger.debug(debug_string)


class MessagebusConnection(MessagebusListener):
	def __init__(self) -> None:
		MessagebusListener.__init__(self)
		self.should_close = False
		self.service_worker_channel: str | None = None
		self.channel_subscription_event = Event()
		self.terminal_open_event = Event()
		self.service_client = get_service_connection()

	def message_received(self, message: Message) -> None:
		log_message(message)
		try:
			self._process_message(message)
		except Exception as err:  # pylint: disable=broad-except
			logger.error(err, exc_info=True)

	def _process_message(self, message: Message) -> None:
		if isinstance(message, ChannelSubscriptionEventMessage):
			# Get responsible service_worker
			self.service_worker_channel = message.sender
			self.channel_subscription_event.set()
		elif isinstance(message, TerminalOpenEventMessage):
			self.terminal_open_event.set()
		elif isinstance(message, TerminalDataReadMessage):
			sys.stdout.buffer.write(message.data)
			sys.stdout.flush()  # This actually pops the buffer to terminal (without waiting for '\n')
		elif isinstance(message, TerminalCloseEventMessage):
			logger.notice("received terminal close event - shutting down")
			sys.stdout.buffer.write(b"\nreceived terminal close event - press Enter to return to local shell\n")
			sys.stdout.flush()  # This actually pops the buffer to terminal (without waiting for '\n')
			self.should_close = True

	def transmit_input(self, term_write_channel: str, term_id: str) -> None:
		while not self.should_close:
			if platform.system().lower() == "windows":
				data = msvcrt.getch()  # type: ignore
			else:
				data = sys.stdin.read(1).encode("utf-8")
			if not data:  # or data == b"\x03":  # Ctrl+C
				self.should_close = True
				break
			tdw = TerminalDataWriteMessage(sender="@", channel=term_write_channel, terminal_id=term_id, data=data)
			log_message(tdw)
			self.service_client.messagebus.send_message(tdw)

	def run_terminal(self, target: str, term_id: Optional[str] = None) -> None:
		if not self.service_client.connected:
			self.service_client.connect()
		self.service_client.connect_messagebus()
		open_new_terminal = False
		with self.register(self.service_client.messagebus):
			# If service_worker_channel is not set, wait for channel_subscription_event
			if not self.service_worker_channel and not self.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
				raise ConnectionError("Failed to subscribe to session channel.")
			if not term_id:
				term_id = str(uuid4())
				open_new_terminal = True
			term_read_channel = f"session:{term_id}"
			if target.lower() == "configserver":
				term_write_channel = f"{self.service_worker_channel}:terminal"
			else:
				term_write_channel = f"host:{target}"

			self.channel_subscription_event.clear()
			csr = ChannelSubscriptionRequestMessage(sender="@", operation="add", channels=[term_read_channel], channel="service:messagebus")
			logger.notice("Requesting access to terminal session channel")
			log_message(csr)
			self.service_client.messagebus.send_message(csr)

			if open_new_terminal:
				if not self.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
					raise ConnectionError("Could not subscribe to terminal session channel")
				size = shutil.get_terminal_size()
				tor = TerminalOpenRequestMessage(
					sender="@",
					channel=term_write_channel,
					terminal_id=term_id,
					back_channel=term_read_channel,
					rows=size.lines,
					cols=size.columns,
				)
				logger.notice("Requesting to open new terminal with id %s ", term_id)
				log_message(tor)
				self.service_client.messagebus.send_message(tor)
			else:
				logger.notice("Requesting access to existing terminal with id %s ", term_id)

			if not self.terminal_open_event.wait(CHANNEL_SUB_TIMEOUT):
				raise ConnectionError("Could not subscribe to terminal session channel")
			logger.notice("Return to local shell with 'exit' or 'Ctrl+D'")
			with stream_wrap():
				self.transmit_input(term_write_channel, term_id)
