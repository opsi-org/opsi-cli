"""
test_terminal
"""

from unittest.mock import patch
from uuid import uuid4

import pytest

from opsicli.messagebus import Message, TerminalMessagebusConnection

from .utils import container_connection


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_terminal() -> None:
	messages = []

	def send_message(message: Message) -> None:
		nonlocal messages
		messages.append(message)

	with patch("opsicli.messagebus.MessagebusConnection.send_message", send_message):
		with container_connection():
			connection = TerminalMessagebusConnection()
			assert connection
			connection.terminal_id = str(uuid4())
			with connection.connection():
				connection.open_terminal("configserver")
				assert connection._terminal_read_channel
				assert connection._terminal_write_channel


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_reconnect() -> None:
	with container_connection():
		for iteration in range(2):
			connection = TerminalMessagebusConnection()
			connection.terminal_id = str(uuid4())
			print(f"Iteration {iteration} terminal_id: {connection.terminal_id}")
			with connection.connection():
				print(f"Iteration {iteration} getting channel pair")
				connection.open_terminal("configserver")


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_with_two_connections() -> None:
	term_id = str(uuid4())

	messages = []

	def send_message(message: Message) -> None:
		nonlocal messages
		messages.append(message)

	with patch("opsicli.messagebus.MessagebusConnection.send_message", send_message):
		with container_connection():
			first = TerminalMessagebusConnection()
			first.terminal_id = term_id
			second = TerminalMessagebusConnection()
			second.terminal_id = term_id
			with first.connection():
				first.open_terminal("configserver")

				with second.connection():
					second.open_terminal("configserver")
