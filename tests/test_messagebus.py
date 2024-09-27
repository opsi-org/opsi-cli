"""
test_messagebus
"""

import time
from threading import Thread

import pytest
from opsicommon.client.opsiservice import ServiceClient

from opsicli.messagebus import JSONRPCMessagebusConnection
from opsicli.opsiservice import get_service_connection

from .utils import container_connection, run_cli


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
	assert result[0].getType() == "OpsiConfigserver"


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
			assert result[0].getType() == "OpsiConfigserver"


@pytest.mark.xfail  # may fail if runner is slow
@pytest.mark.requires_testcontainer
def test_wait_for_event() -> None:
	class CreateHostThread(Thread):
		def __init__(self, client: ServiceClient) -> None:
			super().__init__(daemon=True)
			self.client = client

		def run(self) -> None:
			time.sleep(4.0)
			self.client.jsonrpc("host_createOpsiClient", params=["dummy.test.tld"])

	with container_connection():
		service_connection = get_service_connection()
		cht = CreateHostThread(service_connection)
		cht.start()
		# with tmp_client(connection, CLIENT1):
		cmd = ["-l", "7", "messagebus", "wait-for-event", "host_created", "--timeout", "4"]
		exit_code, _stdout, _stderr = run_cli(cmd)
		cht.join()
		service_connection.jsonrpc("host_delete", params=["dummy.test.tld"])
		assert exit_code == 0  # 'host_created' event found

		cmd = ["messagebus", "wait-for-event", "host_created", "--timeout", "1"]
		exit_code, _stdout, _stderr = run_cli(cmd)
		assert exit_code == 1  # timeout reached


@pytest.mark.xfail  # may fail if runner is slow
@pytest.mark.requires_testcontainer
def test_wait_for_event_data() -> None:
	class CreateHostThread(Thread):
		def __init__(self, client: ServiceClient) -> None:
			super().__init__(daemon=True)
			self.client = client

		def run(self) -> None:
			time.sleep(4.0)
			self.client.jsonrpc("host_createOpsiClient", params=["dummy.test.tld"])

	with container_connection():
		service_connection = get_service_connection()
		cht = CreateHostThread(service_connection)
		cht.start()
		# with tmp_client(connection, CLIENT1):
		cmd = ["-l", "7", "messagebus", "wait-for-event", "host_created", "--data", "id=dummy.test.tld", "--timeout", "4"]
		exit_code, _stdout, _stderr = run_cli(cmd)
		cht.join()
		service_connection.jsonrpc("host_delete", params=["dummy.test.tld"])
		assert exit_code == 0  # 'host_created' event found

		cht = CreateHostThread(service_connection)
		cht.start()
		# with tmp_client(connection, CLIENT1):
		cmd = ["-l", "7", "messagebus", "wait-for-event", "host_created", "--data", "id=some.other.host", "--timeout", "4"]
		exit_code, _stdout, _stderr = run_cli(cmd)
		cht.join()
		service_connection.jsonrpc("host_delete", params=["dummy.test.tld"])
		assert exit_code == 1  # timeout reached
