"""
test_support
"""

import pytest

from .utils import container_connection, run_cli


@pytest.mark.requires_testcontainer
def test_healthcheck() -> None:
	with container_connection():
		exit_code, stdout, _stderr = run_cli(["--output-format=json", "support", "health-check"])
		assert exit_code == 0
		keywords = ("opsiconfd_config", "disk_usage", "redis", "mysql")
		for word in keywords:
			assert word in stdout


@pytest.mark.requires_testcontainer
def test_healthcheck_detailed() -> None:
	with container_connection():
		exit_code, stdout, _stderr = run_cli(["--output-format=json", "support", "health-check", "--detailed"])
		assert exit_code == 0
		assert "No problems detected" in stdout
		exit_code, stdout, _stderr = run_cli(["--output-format=json", "support", "health-check", "mysql"])
		assert exit_code == 0
		assert "Connection to MySQL is working" in stdout


# test_support_client_logs requires live client
