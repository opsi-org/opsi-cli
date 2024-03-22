"""
test_opsiservice
"""

import time
from pathlib import Path

import pytest

from opsicli.cache import cache
from opsicli.config import OPSIService, config
from opsicli.opsiservice import (
	get_service_connection,
	get_service_credentials_from_backend,
	jsonrpc_client,  # noqa: F401
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
	global jsonrpc_client
	jsonrpc_client = None
	config.services.append(OPSIService("pytest_test_service", "https://localhost:4447"))
	config.service = "pytest_test_service"
	connection = get_service_connection()
	result = connection.jsonrpc("backend_getInterface")
	print(result)
	assert "host_getObjects" in str(result)


@pytest.mark.skipif(not Path("/etc/opsi/backends").exists(), reason="need local backend for this test")
def test_get_service_connection_session_handling() -> None:
	del cache._data["opsiconfd-session"]

	get_service_connection()  # first connection
	session_cookie1 = cache.get("opsiconfd-session")
	assert session_cookie1

	get_service_connection()  # second connection
	session_cookie2 = cache.get("opsiconfd-session")

	assert session_cookie1 == session_cookie2


@pytest.mark.skipif(not Path("/etc/opsi/backends").exists(), reason="need local backend for this test")
def test_get_service_connection_session_expired() -> None:
	session_lifetime = 1
	session_cookie = "aDummySessionCookie"
	cache.set("opsiconfd-session", f"opsiconfd-session={session_cookie}", session_lifetime)

	wait_time = session_lifetime + 1
	time.sleep(wait_time)
	connection = get_service_connection()
	assert connection

	session_cookie_new = cache.get("opsiconfd-session")

	assert session_cookie_new != session_cookie


@pytest.mark.requires_testcontainer
def test_get_service_connection() -> None:
	with container_connection():
		connection = get_service_connection()
		assert connection
		result = connection.jsonrpc("backend_getInterface")
		print(result)
		assert "host_getObjects" in str(result)
