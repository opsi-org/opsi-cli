"""
test_terminal
"""

import time

import pytest

from opsicli.messagebus import CHANNEL_SUB_TIMEOUT, MessagebusConnection

from .utils import container_connection


@pytest.mark.requires_testcontainer
def test_messagebus(capsys: pytest.CaptureFixture[str]) -> None:
	with container_connection():
		connection = MessagebusConnection()
		connection.prepare_terminal_connection()
		with connection.register(connection.service_client.messagebus):
			# If service_worker_channel is not set, wait for channel_subscription_event
			if not connection.service_worker_channel and not connection.channel_subscription_event.wait(CHANNEL_SUB_TIMEOUT):
				raise ConnectionError("Failed to subscribe to session channel.")
			(_, term_write_channel) = connection.get_terminal_channel_pair("configserver")
			time.sleep(2)
			connection.transmit_input(term_write_channel, b"whoami\nexit\n")
			time.sleep(0.5)
			capture = capsys.readouterr()
			assert "opsiconfd" in capture.out
			assert "received terminal close event - press Enter to return to local shell" in capture.out
