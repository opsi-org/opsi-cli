"""
test_messagebus
"""

from uuid import uuid4

import pytest

from opsicli.messagebus import CHANNEL_SUB_TIMEOUT, MessagebusConnection

from .utils import container_connection


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc() -> None:
	with container_connection():
		connection = MessagebusConnection()
		assert connection
		result = connection.jsonrpc("service:config:jsonrpc", "backend_info")
	assert "opsiVersion" in result


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc_params() -> None:
	with container_connection():
		connection = MessagebusConnection()
		assert connection
		result = connection.jsonrpc("service:config:jsonrpc", "host_getObjects", ([], {"type": "OpsiConfigserver"}))
	assert len(result) == 1
	assert result[0]["type"] == "OpsiConfigserver"


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc_error() -> None:
	with container_connection():
		connection = MessagebusConnection()
		assert connection
		result = connection.jsonrpc("service:config:jsonrpc", "method_which_does_not_exist")
	assert "data" in result
	assert result["data"].get("class") == "ValueError"
	assert "Invalid method" in result["data"].get("details")


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc_multiple() -> None:
	with container_connection():
		connection = MessagebusConnection()
		assert connection
		result = connection.jsonrpc("service:config:jsonrpc", "backend_info")
		assert "opsiVersion" in result
		assert connection.jsonrpc_response is None
		result = connection.jsonrpc("service:config:jsonrpc", "backend_info")
		assert "opsiVersion" in result


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_terminal() -> None:
	with container_connection():
		connection = MessagebusConnection()
		assert connection
		connection.terminal_id = str(uuid4())
		with connection.connection():
			if not connection.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
				raise ConnectionError("Failed to subscribe to session channel.")
			(term_read_channel, term_write_channel) = connection.get_terminal_channel_pair("configserver")
	assert term_read_channel
	assert term_write_channel


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_reconnect() -> None:
	with container_connection():
		for iteration in range(2):
			connection = MessagebusConnection()
			connection.terminal_id = str(uuid4())
			print(f"Iteration {iteration} terminal_id: {connection.terminal_id}")
			with connection.connection():
				if not connection.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
					raise ConnectionError("Failed to subscribe to session channel (first try).")
				print(f"Iteration {iteration} getting channel pair")
				connection.get_terminal_channel_pair("configserver")


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_with_two_connections() -> None:
	term_id = str(uuid4())
	with container_connection():
		first = MessagebusConnection()
		first.terminal_id = term_id
		second = MessagebusConnection()
		second.terminal_id = term_id
		with first.connection():
			first.get_terminal_channel_pair("configserver")

			with second.connection():
				second.get_terminal_channel_pair("configserver", open_new_terminal=False)
