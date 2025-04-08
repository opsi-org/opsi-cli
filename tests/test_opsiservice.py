"""
test_opsiservice
"""

import time

import pytest

from opsicli.cache import cache
from opsicli.opsiservice import get_service_connection

from .utils import admin_service_config


@pytest.mark.opsi_service
def test_get_service_connection() -> None:
	with admin_service_config():
		local_connection = get_service_connection()
		assert local_connection
		result = local_connection.jsonrpc("backend_getInterface")
		assert "host_getObjects" in str(result)


@pytest.mark.opsi_service
def test_get_service_connection_session_handling() -> None:
	with admin_service_config():
		get_service_connection()  # first connection
		session_cookie1 = cache.get("opsiconfd-session")
		assert session_cookie1

		get_service_connection()  # second connection
		session_cookie2 = cache.get("opsiconfd-session")

		assert session_cookie1 == session_cookie2


@pytest.mark.opsi_service
def test_get_service_connection_session_expired() -> None:
	with admin_service_config():
		session_lifetime = 1
		session_cookie = "aDummySessionCookie"
		cache.set("opsiconfd-session", f"opsiconfd-session={session_cookie}", session_lifetime)

		wait_time = session_lifetime + 1
		time.sleep(wait_time)
		connection = get_service_connection()
		assert connection

		session_cookie_new = cache.get("opsiconfd-session")

		assert session_cookie_new != session_cookie
