"""
test_messagebus
"""

import time

import pytest

from opsicli.messagebus import CHANNEL_SUB_TIMEOUT, MessagebusConnection

from .utils import container_connection


@pytest.mark.requires_testcontainer
def test_messagebus() -> None:
	with container_connection():
		connection = MessagebusConnection()
		assert connection
		connection.prepare_terminal_connection()
		with connection.register(connection.service_client.messagebus):
			if not connection.service_worker_channel and not connection.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
				raise ConnectionError("Failed to subscribe to session channel.")
			connection.get_terminal_channel_pair("configserver")
			assert connection.service_worker_channel
			time.sleep(1)


@pytest.mark.xfail  # TODO: fix second connection / cleanup (or test?)
@pytest.mark.requires_testcontainer
def test_messagebus_reconnect() -> None:
	with container_connection():
		for iteration in range(2):
			connection = MessagebusConnection()
			connection.prepare_terminal_connection()
			print(f"Iteration {iteration} terminal_id: {connection.terminal_id}")
			with connection.register(connection.service_client.messagebus):
				if not connection.service_worker_channel and not connection.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
					raise ConnectionError("Failed to subscribe to session channel (first try).")
				print(f"Iteration {iteration} getting channel pair")
				connection.get_terminal_channel_pair("configserver")
				time.sleep(1)


@pytest.mark.xfail  # TODO: fix second connection / cleanup (or test?)
@pytest.mark.requires_testcontainer
def test_messagebus_with_two_connections() -> None:
	with container_connection():
		first = MessagebusConnection()
		first.prepare_terminal_connection()
		second = MessagebusConnection()
		second.prepare_terminal_connection(first.terminal_id)
		with first.register(first.service_client.messagebus):
			if not first.service_worker_channel and not first.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
				raise ConnectionError("Failed to subscribe to session channel (first try).")
			first.get_terminal_channel_pair("configserver")

			with second.register(second.service_client.messagebus):
				if not second.service_worker_channel and not second.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
					raise ConnectionError("Failed to subscribe to session channel (second try).")
				second.get_terminal_channel_pair("configserver", open_new_terminal=False)
