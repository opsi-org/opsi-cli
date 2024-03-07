"""
test_jsonrpc
"""

import pytest

from .utils import container_connection, run_cli


@pytest.mark.requires_testcontainer
def test_connection() -> None:
	with container_connection():
		exit_code, stdout, _stderr = run_cli(["jsonrpc", "methods"])
		print(stdout)
		assert exit_code == 0
		assert "host_getObjects" in stdout


@pytest.mark.requires_testcontainer
def test_create_delete_object() -> None:
	with container_connection():
		testclient = "pytest-client.test.tld"
		exit_code, stdout, _stderr = run_cli(["jsonrpc", "execute", "host_createOpsiClient", testclient])
		print(stdout)
		assert exit_code == 0
		exit_code, stdout, _stderr = run_cli(["jsonrpc", "execute", "host_getObjects", "[]", f'{{"id": "{testclient}"}}'])
		print(stdout)
		assert exit_code == 0
		assert testclient in stdout
		exit_code, stdout, _stderr = run_cli(["jsonrpc", "execute", "host_delete", testclient])
		print(stdout)
		assert exit_code == 0
		exit_code, stdout, _stderr = run_cli(["jsonrpc", "execute", "host_getObjects", "[]", f'{{"id": "{testclient}"}}'])
		print(stdout)
		assert exit_code == 0
		assert testclient not in stdout
