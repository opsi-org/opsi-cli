"""
test_depot
"""

import pytest

from opsicli.opsiservice import get_service_connection

from .utils import (
	container_connection,
	run_cli,
)


@pytest.mark.requires_testcontainer
def test_depot_execute() -> None:
	with container_connection():
		connection = get_service_connection()
		configserver = connection.jsonrpc("host_getObjects", params=[[], {"type": "OpsiConfigserver"}])[0].id
		cmd = ["depot", "--depots", configserver, "execute", "whoami"]
		exit_code, stdout, stderr = run_cli(cmd)
		print(stderr)
		print(stdout)
		assert exit_code in (0, 1)
		if exit_code == 0:  # necessary module is licensed
			assert f"service:depot:{configserver}:process" in stdout and "opsiconfd" in stdout
		else:  # necessary module is not licensed
			assert f"service:depot:{configserver}:process" in stderr and "Failed to start process" in stderr
