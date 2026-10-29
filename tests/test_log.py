# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_log
"""

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner
from opsi.opsi.service.client import ServiceClient

from opsicli.io import LOG_COLORS, OutputType
from opsicli.messagebus import FileTransferMessagebusConnection
from opsicli.opsiservice import get_service_connection
from plugins.log.python import cli, view_command

from .utils import admin_service_config, run_cli


@pytest.mark.parametrize(
	("log_type", "live", "log_path"),
	[
		("opsiclientd", False, "/var/log/opsi/clientconnect/client.test.tld.log"),
		("opsiclientd", True, "{OPSICLIENTD_LOG_FILE_PATH}"),
		("opsi-script", False, "/var/log/opsi/instlog/client.test.tld.log"),
		("opsi-script", True, "{OPSI_SCRIPT_LOG_FILE_PATH}"),
		("opsiconfd", False, "/var/log/opsi/opsiconfd/opsiconfd.log"),
	],
)
def test_view_command_log_path(log_type: str, live: bool, log_path: str) -> None:
	with patch("plugins.log.python.FileTransferMessagebusConnection") as connection_class:
		connection_class.return_value.view_file = AsyncMock()
		asyncio.run(view_command("client.test.tld", log_type, live, True, 4))
		connection_class.assert_called_once_with(host_id="client.test.tld", log_type=log_type, log_level=4, live=live, follow=True)
		connection_class.return_value.view_file.assert_awaited_once_with(log_path)


@pytest.mark.parametrize("log_type", ["opsiclientd", "opsi-script"])
@pytest.mark.parametrize("live", [False, True])
def test_client_log_channel(log_type: str, live: bool) -> None:
	connection = MagicMock()
	connection.host_id = "client.test.tld"
	connection.log_type = log_type
	connection.live = live
	connection._get_configserver_id.return_value = "server.test.tld"
	connection.service_client.host_getMessagebusConnectedIds.return_value = ["client.test.tld"]
	expected = "host:client.test.tld" if live else "service:depot:server.test.tld:filetransfer"
	assert FileTransferMessagebusConnection._get_channel(connection) == expected


@pytest.mark.parametrize("live", [False, True])
def test_log_view_opsi_script(live: bool) -> None:
	with patch("plugins.log.python.FileTransferMessagebusConnection") as connection_class:
		connection_class.return_value.view_file = AsyncMock()
		args = ["view", "client.test.tld", "--log-type", "opsi-script"]
		if live:
			args.append("--live")
		result = CliRunner().invoke(cli, args)
		assert result.exit_code == 0, result.output
		log_path = "{OPSI_SCRIPT_LOG_FILE_PATH}" if live else "/var/log/opsi/instlog/client.test.tld.log"
		connection_class.return_value.view_file.assert_awaited_once_with(log_path)


def test_view_command_opsiconfd_live_rejected() -> None:
	with pytest.raises(ValueError, match="--live option is only available"):
		asyncio.run(view_command("server.test.tld", "opsiconfd", True, False, 6))


def test_process_opsi_script_log() -> None:
	connection = object.__new__(FileTransferMessagebusConnection)
	connection.log_level = 6
	connection._current_log_level = 6
	lines = [
		"[1] [2026-10-28 16:30:32.458] [] --",
		"[1] [2026-10-28 16:30:32.458] [] --",
		r"[1] [2026-10-28 16:30:32.458] [] c:\opsi.org\log\opsi-script-part-2VAxD802tj.log",
		"[1] [2026-10-28 16:30:32.459] [] opsi-script 4.12.21.1 started at >> 28.10.2026 16:30:32",
	]
	with patch("opsicli.messagebus.console_print") as output:
		for line in lines:
			connection._process_line(line)
		assert [call.args[0].plain for call in output.call_args_list] == lines
		assert all(call.args[0].style == LOG_COLORS["1"] for call in output.call_args_list)
		assert all(call.kwargs["output_type"] == OutputType.DATA for call in output.call_args_list)
	assert connection._current_log_level == 1


@pytest.mark.parametrize("message", ["--", "multiple words", ""])
def test_process_log_level_filter(message: str) -> None:
	connection = object.__new__(FileTransferMessagebusConnection)
	connection.log_level = 6
	connection._current_log_level = 6
	filtered_line = f"[7] [2026-10-28 16:30:32.458] [] {message}"
	visible_line = f"[2] [2026-10-28 16:30:32.459] [] {message}"
	with patch("opsicli.messagebus.console_print") as output:
		connection._process_line(filtered_line)
		connection._process_line("  filtered continuation")
		output.assert_not_called()
		assert connection._current_log_level == 7
		connection._process_line(visible_line)
		connection._process_line("  visible continuation")
		assert [call.args[0].plain for call in output.call_args_list] == [visible_line, "  visible continuation"]
		assert all(call.args[0].style == LOG_COLORS["2"] for call in output.call_args_list)
	assert connection._current_log_level == 2


@pytest.mark.opsi_service
def test_log_view(admin_service_client: ServiceClient) -> None:
	configserver = admin_service_client.jsonrpc("host_getObjects", params=[[], {"type": "OpsiConfigserver"}])[0].id

	log_level = 2
	exit_code, stdout, _ = run_cli(["log", "view", configserver, "--log-type", "opsiconfd", "--log-level", str(log_level)])
	assert exit_code == 0

	log_line_pattern = re.compile(r"\[(\d+)\]")
	lines_to_process = stdout.splitlines()[:1000]
	for line in lines_to_process:
		match = log_line_pattern.match(line)
		if match:
			assert int(match.group(1)) <= log_level


@pytest.mark.opsi_service
def test_file_transfer_messagebus_connection() -> None:
	async def run_test_file_transfer_messagebus_connection() -> None:
		connection = get_service_connection()
		configserver = connection.jsonrpc("host_getObjects", params=[[], {"type": "OpsiConfigserver"}])[0].id

		messagebus_connection_1 = FileTransferMessagebusConnection(
			host_id=configserver, log_type="opsiconfd", log_level=6, live=False, follow=False
		)
		assert messagebus_connection_1

		messagebus_connection_2 = FileTransferMessagebusConnection(
			host_id=configserver, log_type="opsiconfd", log_level=6, live=False, follow=False
		)
		assert messagebus_connection_2

		log_path = "/var/log/opsi/opsiconfd/opsiconfd.log"

		with messagebus_connection_1.connection():
			await messagebus_connection_1.view_file(log_path)
			with messagebus_connection_2.connection():
				await messagebus_connection_1.view_file(log_path)

	with admin_service_config():
		asyncio.run(run_test_file_transfer_messagebus_connection())
