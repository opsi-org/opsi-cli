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
from opsicommon.logging import logger  # type: ignore[import]
from opsicommon.messagebus import (  # type: ignore[import]
	ChannelSubscriptionEventMessage,
	ChannelSubscriptionRequestMessage,
	Message,
	TerminalCloseEvent,
	TerminalDataRead,
	TerminalDataWrite,
	TerminalOpenRequest,
)

from opsicli.opsiservice import get_service_connection
from opsicli.utils import stream_wrap

if platform.system().lower() == "windows":
	import msvcrt  # pylint: disable=import-error

CHANNEL_SUBSCRIPTION_TIMEOUT = 5


def log_message(message: Message) -> None:
	logger.info("Got message of type %s", message.type)
	for key, value in message.to_dict().items():
		logger.debug("\t%s: %s", key, value)


class MessagebusConnection(MessagebusListener):
	def __init__(self) -> None:
		MessagebusListener.__init__(self)
		self.should_close = False
		self.service_worker_channel = None
		self.channel_subscription_event_event = Event()
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
			self.channel_subscription_event_event.set()
		elif isinstance(message, (TerminalDataRead)):
			print(message.data.decode("utf-8"), end="")
			sys.stdout.flush()  # This actually pops the buffer to terminal (without waiting for '\n')
		elif isinstance(message, TerminalCloseEvent):
			logger.notice("received terminal close event - shutting down")
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
			tdw = TerminalDataWrite(sender="@", channel=term_write_channel, terminal_id=term_id, data=data)
			log_message(tdw)
			self.service_client.messagebus.send_message(tdw)

	def run_terminal(self, term_id: Optional[str] = None, target: Optional[str] = None) -> None:
		if not self.service_client.connected:
			self.service_client.connect()
		self.service_client.connect_messagebus()
		with self.register(self.service_client.messagebus):
			# If service_worker_channel is not set, wait for channel_subscription_event
			if not self.service_worker_channel and not self.channel_subscription_event_event.wait(CHANNEL_SUBSCRIPTION_TIMEOUT):
				raise ConnectionError("Failed to subscribe to session channel.")
			term_write_channel = f"{self.service_worker_channel}:terminal"
			term_read_channel = f"session:{term_id}"
			if target:
				term_write_channel = f"host:{target}"

			if not term_id:
				term_id = str(uuid4())
				term_read_channel = f"session:{term_id}"
				size = shutil.get_terminal_size()
				logger.notice("Requesting to open new terminal with id %s ", term_id)
				tor = TerminalOpenRequest(
					sender="@",
					channel=term_write_channel,
					terminal_id=term_id,
					back_channel=term_read_channel,
					rows=size.lines,
					cols=size.columns,
				)
				log_message(tor)
				self.service_client.messagebus.send_message(tor)
			else:
				logger.notice("Requesting access to existing terminal with id %s ", term_id)

			self.channel_subscription_event_event.clear()
			csr = ChannelSubscriptionRequestMessage(sender="@", operation="add", channels=[term_read_channel], channel="service:messagebus")
			log_message(csr)
			self.service_client.messagebus.send_message(csr)

			if not self.channel_subscription_event_event.wait(CHANNEL_SUBSCRIPTION_TIMEOUT):
				raise ConnectionError("Could not subscribe to terminal session channel")
			with stream_wrap():
				self.transmit_input(term_write_channel, term_id)
