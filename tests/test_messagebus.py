"""
test_messagebus
"""

import pytest

from opsicli.messagebus import CHANNEL_SUB_TIMEOUT, MessagebusConnection

from .utils import container_connection


@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc() -> None:
	with container_connection():
		connection = MessagebusConnection()
		assert connection
		result = connection.jsonrpc("service:config:jsonrpc", "backend_info")
	assert "opsiVersion" in result


@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc_params() -> None:
	with container_connection():
		connection = MessagebusConnection()
		assert connection
		result = connection.jsonrpc("service:config:jsonrpc", "host_getObjects", ([], {"type": "OpsiConfigserver"}))
	assert len(result) == 1
	assert result[0]["type"] == "OpsiConfigserver"


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


@pytest.mark.requires_testcontainer
def test_messagebus_terminal() -> None:
	with container_connection():
		connection = MessagebusConnection()
		assert connection
		connection.prepare_terminal_connection()
		assert connection.terminal_id
		with connection.register(connection.service_client.messagebus):
			if not connection.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
				raise ConnectionError("Failed to subscribe to session channel.")
			(term_read_channel, term_write_channel) = connection.get_terminal_channel_pair("configserver")
	assert term_read_channel
	assert term_write_channel


@pytest.mark.requires_testcontainer
def test_messagebus_reconnect() -> None:
	with container_connection():
		for iteration in range(2):
			connection = MessagebusConnection()
			connection.prepare_terminal_connection()
			print(f"Iteration {iteration} terminal_id: {connection.terminal_id}")
			with connection.register(connection.service_client.messagebus):
				if not connection.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
					raise ConnectionError("Failed to subscribe to session channel (first try).")
				print(f"Iteration {iteration} getting channel pair")
				connection.get_terminal_channel_pair("configserver")


@pytest.mark.requires_testcontainer
def test_messagebus_with_two_connections() -> None:
	with container_connection():
		first = MessagebusConnection()
		first.prepare_terminal_connection()
		second = MessagebusConnection()
		second.prepare_terminal_connection(first.terminal_id)
		with first.register(first.service_client.messagebus):
			# if not first.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
			# 	raise ConnectionError("Failed to subscribe to session channel (first try).")
			# first.channel_subscription_event.clear()
			first.get_terminal_channel_pair("configserver")

			with second.register(second.service_client.messagebus):
				# if not second.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
				# 	raise ConnectionError("Failed to subscribe to session channel (second try).")
				# second.channel_subscription_event.clear()
				second.get_terminal_channel_pair("configserver", open_new_terminal=False)
