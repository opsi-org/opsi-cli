# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_jsonrpc
"""

import pytest

from .utils import run_cli


@pytest.mark.opsi_service
def test_connection() -> None:
	exit_code, stdout, _stderr = run_cli(["jsonrpc", "methods"])
	print(stdout)
	assert exit_code == 0
	assert "host_getObjects" in stdout


@pytest.mark.opsi_service
def test_create_delete_object() -> None:
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


@pytest.mark.opsi_service
def test_timeout() -> None:
	exit_code, stdout, _stderr = run_cli(["jsonrpc", "execute", "host_getObjects"])
	assert exit_code == 0

	exit_code, stdout, _stderr = run_cli(["jsonrpc", "execute", "host_getObjects", "--timeout=0.000001"])
	print(stdout)
	assert exit_code != 0


@pytest.mark.opsi_service
def test_deprecation_warning() -> None:
	exit_code, _stdout, stderr = run_cli(["jsonrpc", "execute", "host_getHashes"])
	assert exit_code == 0
	assert "Method 'host_getHashes' is deprecated" in stderr
