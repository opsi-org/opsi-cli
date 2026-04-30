# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_opsiservice
"""

import time
from typing import Any
from unittest.mock import patch

import pytest

from opsicli.cache import cache
from opsicli.config import config
from opsicli.opsiservice import get_service_connection

from .utils import admin_service_config


class MockServiceClient:
	def register_connection_listener(self, listener: Any) -> None:
		pass

	def connect(self) -> None:
		pass


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


def test_get_service_connection_uses_totp_value() -> None:
	config.service = "https://testhost:4447"
	config.username = "testuser"
	config.password = "testpassword"
	config.totp = True
	config.totp_value = "123456"

	with patch("opsicli.opsiservice.prompt") as mock_prompt, patch("opsicli.opsiservice.get_service_client") as mock_get_service_client:
		mock_get_service_client.return_value = MockServiceClient()

		get_service_connection()

	mock_prompt.assert_not_called()
	mock_get_service_client.assert_called_once()
	assert mock_get_service_client.call_args.kwargs["totp"] == "123456"


def test_get_service_connection_prompts_for_totp_without_totp_value() -> None:
	config.service = "https://testhost:4447"
	config.username = "testuser"
	config.password = "testpassword"
	config.totp = True

	with (
		patch("opsicli.opsiservice.prompt", return_value="654321") as mock_prompt,
		patch("opsicli.opsiservice.get_service_client") as mock_get_service_client,
	):
		mock_get_service_client.return_value = MockServiceClient()

		get_service_connection()

	mock_prompt.assert_called_once_with("Enter the TOTP", password=True)
	mock_get_service_client.assert_called_once()
	assert mock_get_service_client.call_args.kwargs["totp"] == "654321"
