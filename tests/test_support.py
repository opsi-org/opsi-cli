# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_support
"""

from pathlib import Path
from unittest.mock import call, patch

import pytest
from click.testing import CliRunner

from plugins.support.python import cli

from .utils import run_cli


@pytest.mark.parametrize("content_length", ["11", "0", None])
def test_client_logs_download_progress(tmp_path: Path, content_length: str | None) -> None:
	with (
		patch("plugins.support.python.JSONRPCMessagebusConnection") as messagebus_class,
		patch("plugins.support.python.get_service_connection") as get_service,
		patch("plugins.support.python.get_progress") as get_progress,
	):
		messagebus_class.return_value.jsonrpc.return_value = {"host:client.test.tld": {"file_id": "archive-id"}}
		response = get_service.return_value.get.return_value
		response.headers = {"Content-Length": content_length} if content_length is not None else {}
		response.iter_content.return_value = iter([b"first", b"", b"second"])
		progress = get_progress.return_value.__enter__.return_value
		task = progress.add_task.return_value

		result = CliRunner().invoke(cli, ["client-logs", "client.test.tld", "--path", str(tmp_path)])

		assert result.exit_code == 0, result.output
		assert (tmp_path / "client.test.tld.zip").read_bytes() == b"firstsecond"
		get_service.return_value.get.assert_called_once_with("/file-transfer/archive-id", raw_response=True)
		response.iter_content.assert_called_once_with(chunk_size=8192)
		progress.add_task.assert_called_once_with("Downloading client.test.tld.zip", total=11 if content_length == "11" else None)
		assert progress.advance.call_args_list == [call(task, 5), call(task, 6)]
		if content_length == "11":
			progress.update.assert_not_called()
		else:
			progress.update.assert_called_once_with(task, total=11)
		get_progress.return_value.__exit__.assert_called_once()


@pytest.mark.opsi_service
def test_healthcheck() -> None:
	exit_code, stdout, _stderr = run_cli(["--output-format=json", "support", "health-check"])
	print(stdout)
	print(_stderr)
	assert exit_code == 0
	keywords = ("opsiconfd_config", "disk_usage", "redis", "mysql")
	for word in keywords:
		assert word in stdout


@pytest.mark.opsi_service
def test_healthcheck_detailed() -> None:
	exit_code, stdout, _stderr = run_cli(["--output-format=json", "support", "health-check", "--detailed"])
	assert exit_code == 0
	assert "No problems detected" in stdout
	exit_code, stdout, _stderr = run_cli(["--output-format=json", "support", "health-check", "mysql"])
	assert exit_code == 0
	assert "No MySQL issues found." in stdout
