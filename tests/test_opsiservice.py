"""
test_opsiservice
"""

from pathlib import Path

import pytest

from opsicli.config import OPSIService, config
from opsicli.opsiservice import jsonrpc_client  # pylint: disable=unused-import
from opsicli.opsiservice import (
	get_service_connection,
	get_service_credentials_from_backend,
)

from .utils import container_connection


@pytest.mark.skipif(not Path("/etc/opsi/backends").exists(), reason="need local backend for this test")
def test_get_service_credentials_from_backend() -> None:
	(host_id, host_key) = get_service_credentials_from_backend()
	assert host_id
	assert host_key


@pytest.mark.skipif(not Path("/etc/opsi/backends").exists(), reason="need local backend for this test")
def test_get_service_connection_local() -> None:
	local_connection = get_service_connection()
	assert local_connection
	result = local_connection.jsonrpc("backend_getInterface")
	print(result)
	assert "host_getObjects" in str(result)


@pytest.mark.skipif(not Path("/etc/opsi/backends").exists(), reason="need local backend for this test")
def test_get_service_connection_half_configured_service() -> None:
	global jsonrpc_client  # pylint: disable=global-statement
	jsonrpc_client = None
	config.services.append(OPSIService("pytest_test_service", "https://localhost:4447"))
	config.service = "pytest_test_service"
	connection = get_service_connection()
	result = connection.jsonrpc("backend_getInterface")
	print(result)
	assert "host_getObjects" in str(result)


@pytest.mark.requires_testcontainer
def test_get_service_connection() -> None:
	with container_connection() as connection:
		connection = get_service_connection()
		assert connection
		result = connection.jsonrpc("backend_getInterface")
		print(result)
		assert "host_getObjects" in str(result)