"""
test_messagebus
"""

import pytest

from opsicli.messagebus import JSONRPCMessagebusConnection

from .utils import container_connection


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc() -> None:
	with container_connection():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			assert connection
			result = connection.jsonrpc(["service:config:jsonrpc"], "backend_info")["service:config:jsonrpc"]
	assert "opsiVersion" in result


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc_params() -> None:
	with container_connection():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			result = connection.jsonrpc(["service:config:jsonrpc"], "host_getObjects", ([], {"type": "OpsiConfigserver"}))[
				"service:config:jsonrpc"
			]
	assert len(result) == 1
	assert result[0]["type"] == "OpsiConfigserver"


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc_error() -> None:
	with container_connection():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			result = connection.jsonrpc(["service:config:jsonrpc"], "method_which_does_not_exist")["service:config:jsonrpc"]
	assert "data" in result
	assert result["data"].get("class") == "ValueError"
	assert "Invalid method" in result["data"].get("details")


@pytest.mark.xfail
@pytest.mark.requires_testcontainer
def test_messagebus_jsonrpc_multiple() -> None:
	with container_connection():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			result = connection.jsonrpc(["service:config:jsonrpc"], "backend_info")["service:config:jsonrpc"]
			assert "opsiVersion" in result
			result = connection.jsonrpc(["service:config:jsonrpc"], "host_getObjects", ([], {"type": "OpsiConfigserver"}))[
				"service:config:jsonrpc"
			]
			assert result[0]["type"] == "OpsiConfigserver"
