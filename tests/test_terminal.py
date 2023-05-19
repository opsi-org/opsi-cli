"""
test_terminal
"""

import time
from uuid import uuid4

import pytest

from opsicli.messagebus import MessagebusConnection

from .utils import container_connection


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_terminal(capsys: pytest.CaptureFixture[str]) -> None:
	with container_connection():
		connection = MessagebusConnection()
		connection.terminal_id = str(uuid4())
		with connection.connection():
			(_, term_write_channel) = connection.get_terminal_channel_pair("configserver")
			connection.transmit_input(term_write_channel, b"\n\nwhoami\nexit\n")
			time.sleep(1)
			capture = capsys.readouterr()
			assert "opsiconfd" in capture.out
			# This does behave differently in pytest and manual testing.
			# assert "received terminal close event - press Enter to return to local shell" in capture.out
