"""
test_messagebus
"""

import time
from threading import Thread

import pytest
from opsicommon.client.opsiservice import ServiceClient

from opsicli.messagebus import JSONRPCMessagebusConnection
from opsicli.opsiservice import get_service_connection

from .utils import container_connection, run_cli, tmp_client, tmp_product


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


@pytest.mark.parametrize("action_request", ["setup", "uninstall"])
@pytest.mark.parametrize("success", [True, False])
@pytest.mark.requires_testcontainer
def test_wait_for_installation(action_request: str, success: bool) -> None:
	LISTENER_SETUP_WAIT = 2.0  # Waiting to make sure listener is set up
	LISTENING_TIMEOUT = 4.0  # Time to wait for the event to occur

	class FakeInstallationThread(Thread):
		def __init__(self, client: ServiceClient, poc: dict[str, str]) -> None:
			super().__init__(daemon=True)
			self.client = client
			self.poc = poc

		def run(self) -> None:
			time.sleep(LISTENER_SETUP_WAIT)
			self.client.jsonrpc("productOnClient_updateObjects", params=[self.poc])

	with container_connection():
		service_connection = get_service_connection()  # recreate=True
		with (
			tmp_client(service_connection, "client1.test.tld"),
			tmp_product(service_connection, "testproduct"),
		):
			wanted_status = "installed" if action_request == "setup" else "not_installed"
			poc = {
				"clientId": "client1.test.tld",
				"productId": "testproduct",
				"actionRequest": "none",
				"installationStatus": wanted_status if success else "unknown",
				"productType": "LocalbootProduct",
			}
			cht = FakeInstallationThread(service_connection, poc)
			cht.start()
			cmd = [
				"-l7",
				"messagebus",
				"wait-for-installation",
				"client1.test.tld",
				"testproduct",
				action_request,
				"--timeout",
				str(LISTENING_TIMEOUT),
			]
			exit_code, _stdout, _stderr = run_cli(cmd)
			cht.join()
			assert exit_code == 0 if success else 1

	waiting = [
		{"clientId": "client1.test.tld", "productId": "testproduct", "actionRequest": "none", "installationStatus": "installed"},
		{"clientId": "client1.test.tld", "productId": "testproduct", "actionRequest": "none", "installationStatus": "unknown"},
	]
	found = {
		"productId": "testproduct",
		"productType": "LocalbootProduct",
		"clientId": "client1.test.tld",
		"installationStatus": "installed",
		"actionRequest": "none",
	}
