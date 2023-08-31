"""
test_messagebus
"""

import pytest

from opsicli.messagebus import MessagebusConnection

from .utils import container_connection


@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc() -> None:
	with container_connection():
		with MessagebusConnection().connection() as connection:
			assert connection
			result = connection.jsonrpc("service:config:jsonrpc", "backend_info")
	assert "opsiVersion" in result


@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc_params() -> None:
	with container_connection():
		with MessagebusConnection().connection() as connection:
			assert connection
			result = connection.jsonrpc("service:config:jsonrpc", "host_getObjects", ([], {"type": "OpsiConfigserver"}))
	assert len(result) == 1
	assert result[0]["type"] == "OpsiConfigserver"


@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc_error() -> None:
	with container_connection():
		with MessagebusConnection().connection() as connection:
			assert connection
			result = connection.jsonrpc("service:config:jsonrpc", "method_which_does_not_exist")
	assert "data" in result
	assert result["data"].get("class") == "ValueError"
	assert "Invalid method" in result["data"].get("details")


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc_multiple() -> None:
	with container_connection():
		with MessagebusConnection().connection() as connection:
			assert connection
			result = connection.jsonrpc("service:config:jsonrpc", "backend_info")
			assert "opsiVersion" in result
			assert connection.jsonrpc_response is None
			result = connection.jsonrpc("service:config:jsonrpc", "backend_info")
			assert "opsiVersion" in result
