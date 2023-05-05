"""
test_support
"""

import pytest

from .utils import container_connection, run_cli


@pytest.mark.requires_testcontainer
def test_healthcheck() -> None:
	with container_connection():
		exit_code, output = run_cli(["--output-format=json", "support", "health-check"])
		assert exit_code == 0
		keywords = ("opsiconfd_config", "disk_usage", "redis", "mysql")
		for word in keywords:
			assert word in output


# test_support_client_logs requires live client
