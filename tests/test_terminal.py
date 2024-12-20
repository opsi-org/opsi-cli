"""
test_terminal
"""

from uuid import uuid4

import pytest
from opsicommon.client.opsiservice import ServiceClient
from opsicommon.logging import use_logging_config

from opsicli.messagebus import TerminalMessagebusConnection
from opsicli.opsiservice import get_service_connection

from .utils import container_connection


def get_configserver_channel(service_client: ServiceClient) -> str:
	config_servers = service_client.host_getObjects(attributes=["id"], type="OpsiConfigserver")  # type: ignore[attr-defined]
	return f"service:depot:{config_servers[0].id}:terminal"


@pytest.mark.requires_testcontainer
def test_messagebus_terminal() -> None:
	with container_connection():
		connection = TerminalMessagebusConnection()
		assert connection
		connection.terminal_id = str(uuid4())
		with connection.connection():
			with use_logging_config(stderr_level=7):
				connection.open_terminal(get_configserver_channel(connection.service_client))
				assert not connection._terminal_error
				assert connection._terminal_read_channel
				assert connection._terminal_write_channel


@pytest.mark.requires_testcontainer
def test_messagebus_reconnect() -> None:
	with container_connection():
		for iteration in range(2):
			connection = TerminalMessagebusConnection()
			connection.terminal_id = str(uuid4())
			print(f"Iteration {iteration} terminal_id: {connection.terminal_id}")
			with connection.connection():
				print(f"Iteration {iteration} getting channel pair")
				connection.open_terminal(get_configserver_channel(connection.service_client))
				assert not connection._terminal_error


@pytest.mark.requires_testcontainer
def test_messagebus_with_two_connections() -> None:
	term_id = str(uuid4())
	with container_connection():
		first = TerminalMessagebusConnection()
		first.terminal_id = term_id
		get_service_connection.cache_clear()
		second = TerminalMessagebusConnection()
		second.terminal_id = term_id
		with first.connection():
			first.open_terminal(get_configserver_channel(first.service_client))
			assert not first._terminal_error

			with second.connection():
				second.open_terminal(get_configserver_channel(second.service_client))
				assert not second._terminal_error
				assert first._terminal_write_channel == second._terminal_write_channel
				assert first._terminal_read_channel == second._terminal_read_channel
