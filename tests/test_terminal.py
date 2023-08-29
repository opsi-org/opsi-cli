"""
test_terminal
"""

from uuid import uuid4

import pytest

from opsicli.messagebus import TerminalMessagebusConnection

from .utils import container_connection


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_terminal() -> None:
	with container_connection():
		connection = TerminalMessagebusConnection()
		assert connection
		connection.terminal_id = str(uuid4())
		with connection.connection():
			(term_read_channel, term_write_channel) = connection.get_terminal_channel_pair("configserver")
	assert term_read_channel
	assert term_write_channel


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
				connection.get_terminal_channel_pair("configserver")


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_with_two_connections() -> None:
	term_id = str(uuid4())
	with container_connection():
		first = TerminalMessagebusConnection()
		first.terminal_id = term_id
		second = TerminalMessagebusConnection()
		second.terminal_id = term_id
		with first.connection():
			first.get_terminal_channel_pair("configserver")

			with second.connection():
				second.get_terminal_channel_pair("configserver")
