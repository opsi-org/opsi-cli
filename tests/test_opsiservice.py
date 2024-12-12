"""
test_opsiservice
"""

import time
from pathlib import Path

import lz4.frame  # type: ignore[import-untyped]
import pytest
from opsicommon.messagebus import CONNECTION_SESSION_CHANNEL, CONNECTION_USER_CHANNEL
from opsicommon.messagebus.message import ChannelSubscriptionEventMessage, Message, TraceRequestMessage
from opsicommon.testing.helpers import HTTPTestServerRequestHandler, http_test_server

from opsicli.cache import cache
from opsicli.config import OPSIService, config
from opsicli.messagebus import MessagebusConnection
from opsicli.opsiservice import (
	get_service_connection,
	service_client,  # noqa: F401
)

from .utils import container_connection


@pytest.mark.skipif(not Path("/etc/opsi/backends").exists(), reason="need local backend for this test")
def test_get_service_connection_local() -> None:
	local_connection = get_service_connection()
	assert local_connection
	result = local_connection.jsonrpc("backend_getInterface")
	print(result)
	assert "host_getObjects" in str(result)


@pytest.mark.skipif(not Path("/etc/opsi/backends").exists(), reason="need local backend for this test")
def test_get_service_connection_half_configured_service() -> None:
	global service_client
	service_client = None
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


@pytest.mark.xfail  # may fail if runner is slow
def test_get_service_messagebus_connection() -> None:
	subscribed_channels = [
		"chan4",
		"session:33333333-3333-3333-3333-333333333333",
	]
	mb_messages = []

	def ws_connect_callback(handler: HTTPTestServerRequestHandler) -> None:
		msg = ChannelSubscriptionEventMessage(
			sender="service:worker:test:1",
			channel="host:test-client.uib.local",
			subscribed_channels=subscribed_channels,
		)
		handler.ws_send_message(lz4.frame.compress(msg.to_msgpack(), compression_level=0, block_linked=True))

	def ws_message_callback(handler: HTTPTestServerRequestHandler, message: bytes) -> None:
		nonlocal mb_messages
		msg = Message.from_msgpack(lz4.frame.decompress(message))
		mb_messages.append(msg)

	with http_test_server(
		generate_cert=True,
		ws_connect_callback=ws_connect_callback,
		ws_message_callback=ws_message_callback,
		response_headers={"server": "opsiconfd 4.3.0.0 (uvicorn)"},
	) as server:
		config.service = f"https://localhost:{server.port}"
		messagebus_connection = MessagebusConnection(verify="accept_all")
		with messagebus_connection.connection() as connection:
			connection.send_message(
				TraceRequestMessage(sender=CONNECTION_USER_CHANNEL, channel=CONNECTION_SESSION_CHANNEL, payload=b"test", trace={})
			)
			for _ in range(50):
				if mb_messages:
					break
				time.sleep(0.1)
			assert len(mb_messages) == 1
			assert mb_messages[0].type == "trace_request"
			assert mb_messages[0].payload == b"test"  # type: ignore[attr-defined]


@pytest.mark.xfail  # may fail if runner is slow
@pytest.mark.requires_testcontainer
def test_get_service_connection() -> None:
	with container_connection():
		connection = get_service_connection()
		assert connection
		result = connection.jsonrpc("backend_getInterface")
		print(result)
		assert "host_getObjects" in str(result)
