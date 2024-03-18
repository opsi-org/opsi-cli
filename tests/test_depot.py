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
def test_docker_execute() -> None:
	with container_connection():
		connection = get_service_connection()
		configserver = connection.jsonrpc("host_getObjects", params=[[], {"type": "OpsiConfigserver"}])[0]["id"]
		cmd = ["depot", "--depots", configserver, "execute", "whoami"]
		exit_code, output, _stderr = run_cli(cmd)
		print(output)
		assert exit_code == 0
		assert f"service:depot:{configserver}:process: opsiconfd" in output
