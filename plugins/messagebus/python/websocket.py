"""
websocket functions
"""

import asyncio
import shutil
import sys
import termios
import time
import tty
from contextlib import contextmanager
from threading import Event
from typing import Optional
from uuid import uuid4

from opsicommon.client.opsiservice import (
	MessagebusListener,
	ServiceClient,
	ServiceVerificationModes,
)
from opsicommon.logging import logger, logging_config
from opsicommon.messagebus import (
	ChannelSubscriptionEventMessage,
	ChannelSubscriptionRequestMessage,
	Message,
	TerminalCloseEvent,
	TerminalDataRead,
	TerminalDataWrite,
	TerminalOpenRequest,
)

from opsicli.io import prompt

CHANNEL_SUBSCRIPTION_TIMEOUT = 5


@contextmanager
def stream_wrap():
	logging_config(stderr_level=0)  # Restore?
	attrs = termios.tcgetattr(sys.stdin.fileno())
	try:
		tty.setraw(sys.stdin.fileno())
		yield
	except Exception as err:  # pylint: disable=broad-except
		termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, attrs)
		print(err, file=sys.stderr)
	else:
		termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, attrs)


def log_message(message: Message) -> None:
	logger.devel("Got message of type %s", message.type)
	for key, value in message.to_dict().items():
		logger.info("\t%s: %s", key, value)


class MessagebusTerminal(MessagebusListener):
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
		# Get responsible service_worker
		if not self.service_worker_channel and isinstance(message, ChannelSubscriptionEventMessage):
			logger.notice("Got channel subscription event")
			self.service_worker_channel = message.sender
			self.channel_subscription_event.set()
		elif isinstance(message, (TerminalDataRead, TerminalDataWrite)):
			print(message.data.decode("utf-8"), end="")
		elif isinstance(message, TerminalCloseEvent):
			logger.notice("received terminal close event - shutting down")
			self.should_close = True

	async def transmit_input(self, term_write_channel, term_id):
		# max_size = 1024
		# my_stdin = asyncio.StreamReader()
		while not self.should_close:
			# data = await my_stdin.read(max_size)
			data = sys.stdin.read(1)
			# data = "ls\n".encode("utf-8")
			if not data:
				self.should_close = True
			tdw = TerminalDataWrite(sender="@", channel=term_write_channel, terminal_id=term_id, data=data)
			log_message(tdw)
			self.service_client.messagebus.send_message(tdw)

	def run_terminal(self):
		if not self.service_client.connected:
			self.service_client.connect()
		self.service_client.connect_messagebus()

		term_id = str(uuid4())
		term_read_channel = f"session:{term_id}"
		with self.register(self.service_client.messagebus):
			if not (self.channel_subscription_event.wait(CHANNEL_SUBSCRIPTION_TIMEOUT) and self.service_worker_channel):
				logger.error("Failed to subscribe for terminal session channel.")
				return
			term_write_channel = f"{self.service_worker_channel}:terminal"
			size = shutil.get_terminal_size()
			logger.notice(
				"Requesting to open terminal with id %s (channel=%s, back_channel=%s)",
				term_id,
				term_write_channel,
				term_read_channel,
			)
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

			csr = ChannelSubscriptionRequestMessage(sender="@", operation="add", channels=[term_read_channel], channel="service:messagebus")
			log_message(csr)
			self.service_client.messagebus.send_message(csr)

			# time.sleep(1)
			# self.service_client.messagebus.send_message(
			# 	TerminalDataWrite(sender="@", channel=term_write_channel, terminal_id=term_id, data="ls\n".encode("utf-8"))
			# )
			# while True:
			# 	time.sleep(1)

			with stream_wrap():
				asyncio.run(self.transmit_input(term_write_channel, term_id))
