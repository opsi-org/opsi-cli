"""
websocket functions
"""

import platform
import shutil
import sys
from contextlib import contextmanager
from threading import Event
from typing import Optional
from uuid import uuid4

from opsicommon.client.opsiservice import (  # type: ignore[import]
	MessagebusListener,
	ServiceClient,
	ServiceVerificationModes,
)
from opsicommon.logging import logger, logging_config  # type: ignore[import]
from opsicommon.messagebus import (  # type: ignore[import]
	ChannelSubscriptionEventMessage,
	ChannelSubscriptionRequestMessage,
	Message,
	TerminalCloseEvent,
	TerminalDataRead,
	TerminalDataWrite,
	TerminalOpenRequest,
)

from opsicli.io import prompt

if platform.system().lower() == "windows":
	import msvcrt  # pylint: disable=import-error
else:
	import termios
	import tty

CHANNEL_SUBSCRIPTION_TIMEOUT = 5


@contextmanager
def stream_wrap():
	logging_config(stderr_level=0)  # Restore?
	if platform.system().lower() == "windows":
		yield
	else:
		attrs = termios.tcgetattr(sys.stdin.fileno())
		try:
			tty.setraw(sys.stdin.fileno())  # Set raw mode to access char by char
			yield
		except Exception as err:  # pylint: disable=broad-except
			termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, attrs)
			print(err, file=sys.stderr)
		else:
			termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, attrs)


def log_message(message: Message) -> None:
	logger.info("Got message of type %s", message.type)
	for key, value in message.to_dict().items():
		logger.debug("\t%s: %s", key, value)


class MessagebusConnection(MessagebusListener):
	def __init__(self, url: str, username: str, password: Optional[str] = None) -> None:
		from . import __version__  # pylint: disable=import-outside-toplevel

		MessagebusListener.__init__(self)
		verify = ServiceVerificationModes.ACCEPT_ALL

		self.should_close = False
		self.service_worker_channel = None
		self.channel_subscription_event = Event()
		self.service_client = ServiceClient(
			address=url,
			username=username,
			password=password or prompt("password", password=True),
			verify=verify,
			user_agent=f"opsi-cli-messagebus/{__version__}",
		)

	def message_received(self, message: Message) -> None:
		log_message(message)
		try:
			self._process_message(message)
		except Exception as err:  # pylint: disable=broad-except
			logger.error(err, exc_info=True)

	def _process_message(self, message: Message) -> None:
		if not self.service_worker_channel and isinstance(message, ChannelSubscriptionEventMessage):
			logger.notice("Got channel subscription event")
			# Get responsible service_worker
			self.service_worker_channel = message.sender
			self.channel_subscription_event.set()
		elif isinstance(message, (TerminalDataRead)):
			print(message.data.decode("utf-8"), end="")
			sys.stdout.flush()  # This actually pops the buffer to terminal (without waiting for '\n')
		elif isinstance(message, TerminalCloseEvent):
			logger.notice("received terminal close event - shutting down")
			self.should_close = True

	def transmit_input(self, term_write_channel, term_id):
		while not self.should_close:
			if platform.system().lower() == "windows":
				data = msvcrt.getch()
			else:
				data = sys.stdin.read(1)
			if not data:  # or data == "\x03":  # Ctrl+C
				self.should_close = True
				break
			tdw = TerminalDataWrite(sender="@", channel=term_write_channel, terminal_id=term_id, data=data.encode("utf-8"))
			log_message(tdw)
			self.service_client.messagebus.send_message(tdw)

	def run_terminal(self, term_id: Optional[str] = None):
		if not self.service_client.connected:
			self.service_client.connect()
		self.service_client.connect_messagebus()
		with self.register(self.service_client.messagebus):
			if not (self.channel_subscription_event.wait(CHANNEL_SUBSCRIPTION_TIMEOUT) and self.service_worker_channel):
				logger.error("Failed to subscribe to channel.")
				return
			term_write_channel = f"{self.service_worker_channel}:terminal"
			term_read_channel = f"session:{term_id}"

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

			csr = ChannelSubscriptionRequestMessage(sender="@", operation="add", channels=[term_read_channel], channel="service:messagebus")
			log_message(csr)
			self.service_client.messagebus.send_message(csr)

			with stream_wrap():
				self.transmit_input(term_write_channel, term_id)
