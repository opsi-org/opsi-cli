"""
test_log
"""

import asyncio
import re

import pytest

from opsicli.messagebus import FileTransferMessagebusConnection
from opsicli.opsiservice import get_service_connection

from .utils import container_connection, run_cli


@pytest.mark.requires_testcontainer
def test_log_view() -> None:
	with container_connection():
		connection = get_service_connection()
		configserver = connection.jsonrpc("host_getObjects", params=[[], {"type": "OpsiConfigserver"}])[0].id

		log_level = 2
		exit_code, stdout, _ = run_cli(["log", "view", configserver, "--log-type", "opsiconfd", "--log-level", str(log_level), "--color"])
		assert exit_code == 0

		log_line_pattern = re.compile(r"\[(\d+)\]")
		lines_to_process = stdout.splitlines()[:1000]
		for line in lines_to_process:
			match = log_line_pattern.match(line)
			if match:
				log_level = int(match.group(1))
				assert log_level <= log_level


@pytest.mark.requires_testcontainer
def test_file_transfer_messagebus_connection() -> None:
	async def run_test_file_transfer_messagebus_connection() -> None:
		with container_connection():
			connection = get_service_connection()
			configserver = connection.jsonrpc("host_getObjects", params=[[], {"type": "OpsiConfigserver"}])[0].id

			messagebus_connection_1 = FileTransferMessagebusConnection(
				host_id=configserver, log_type="opsiconfd", log_level=6, enable_formatting=False, live=False, follow=False
			)
			assert messagebus_connection_1

			messagebus_connection_2 = FileTransferMessagebusConnection(
				host_id=configserver, log_type="opsiconfd", log_level=6, enable_formatting=False, live=False, follow=False
			)
			assert messagebus_connection_2

			log_path = "/var/log/opsi/opsiconfd/opsiconfd.log"

			with messagebus_connection_1.connection():
				await messagebus_connection_1.view_file(log_path)
				with messagebus_connection_2.connection():
					await messagebus_connection_1.view_file(log_path)

	asyncio.run(run_test_file_transfer_messagebus_connection())
