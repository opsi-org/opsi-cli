# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_messagebus
"""

import json
import time
from threading import Thread

import pytest
from opsicommon.logging import get_logger, log_context

from opsicli.messagebus import JSONRPCMessagebusConnection
from opsicli.opsiservice import get_service_connection

from .conftest import get_admin_service_client, get_host_service_client
from .utils import admin_service_config, run_cli, tmp_client, tmp_product

logger = get_logger()


@pytest.mark.opsi_service
def test_messagebus_jsonrpc() -> None:
	with admin_service_config():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			assert connection
			result = connection.jsonrpc(["service:config:jsonrpc"], "backend_info")["service:config:jsonrpc"]
		assert "opsiVersion" in result


@pytest.mark.opsi_service
def test_messagebus_jsonrpc_params() -> None:
	with admin_service_config():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			result = connection.jsonrpc(["service:config:jsonrpc"], "host_getObjects", ([], {"type": "OpsiConfigserver"}))[
				"service:config:jsonrpc"
			]
		assert len(result) == 1
		assert result[0]["type"] == "OpsiConfigserver"


@pytest.mark.opsi_service
def test_messagebus_jsonrpc_error() -> None:
	with admin_service_config():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			result = connection.jsonrpc(["service:config:jsonrpc"], "method_which_does_not_exist")["service:config:jsonrpc"]
		assert "data" in result["error"]
		assert result["error"]["data"]["class"] == "ValueError"
		assert "Invalid method" in result["error"]["data"]["details"]


@pytest.mark.opsi_service
def test_messagebus_jsonrpc_multiple() -> None:
	with admin_service_config():
		connection = JSONRPCMessagebusConnection()
		with connection.connection():
			result = connection.jsonrpc(["service:config:jsonrpc"], "backend_info")["service:config:jsonrpc"]
			assert "opsiVersion" in result
			result = connection.jsonrpc(["service:config:jsonrpc"], "host_getObjects", ([], {"type": "OpsiConfigserver"}))[
				"service:config:jsonrpc"
			]
			assert result[0]["type"] == "OpsiConfigserver"


@pytest.mark.opsi_service
@pytest.mark.parametrize(
	"types, output_type",
	(
		([], None),
		(["host_created"], "message"),
	),
)
def test_get_events(types: list[str], output_type: str | None) -> None:
	client_id = "dummy1.test.tld"

	class CreateHostThread(Thread):
		def run(self) -> None:
			with log_context({"instance": "CreateHostThread"}):
				with get_admin_service_client() as client:
					time.sleep(7)
					client.jsonrpc("host_createOpsiClient", params=[client_id])
					time.sleep(1)
					client.jsonrpc("host_delete", params=[client_id])

	for cid in (client_id, "some.other.host"):
		cht = CreateHostThread(daemon=True)
		cht.start()
		cmd = ["-l5", "--output-format", "json", "messagebus", "get-events", "--timeout", "10"]
		for event_type in types:
			cmd += ["--type", event_type]
		if output_type:
			cmd += ["--output-type", output_type]

		exit_code, _stdout, _stderr = run_cli(cmd)
		cht.join()
		data = [json.loads(line.strip()) for line in _stdout.splitlines() if line]
		assert len(data) == len(types) if types else 2
		if output_type == "message":
			assert data[0]["sender"]
		else:
			assert "sender" not in data[0]
		assert exit_code == 0


@pytest.mark.opsi_service
@pytest.mark.parametrize("with_data", (True, False))
def test_wait_for_event(with_data: bool) -> None:
	client_id = "dummy1.test.tld"

	class CreateHostThread(Thread):
		def run(self) -> None:
			with log_context({"instance": "CreateHostThread"}):
				with get_admin_service_client() as client:
					time.sleep(7)
					client.jsonrpc("host_createOpsiClient", params=[client_id])
					time.sleep(1)
					client.jsonrpc("host_delete", params=[client_id])

	for cid in (client_id, "some.other.host"):
		cht = CreateHostThread(daemon=True)
		cht.start()
		cmd = ["messagebus", "wait-for-event", "host_created", "--timeout", "10"]
		if with_data:
			cmd += ["--data", f"id={cid}"]
		exit_code, _stdout, _stderr = run_cli(cmd)
		cht.join()
		if with_data and cid != client_id:
			# timeout reached
			assert exit_code == 1
		else:
			# 'host_created' event found
			assert exit_code == 0


@pytest.mark.opsi_service
@pytest.mark.parametrize("installation_status", ["installed", "not_installed"])
@pytest.mark.parametrize("success", [True, False])
def test_wait_for_installation(installation_status: str, success: bool) -> None:
	class FakeInstallationThread(Thread):
		def run(self) -> None:
			with log_context({"instance": "FakeInstallationThread"}):
				with get_admin_service_client() as client:
					time.sleep(7)
					client.jsonrpc(
						"productOnClient_updateObjects",
						params=[
							{
								"clientId": "client1.test.tld",
								"productId": "testproduct",
								"actionResult": "successful" if success else "failed",
								"installationStatus": installation_status if success else "unknown",
								"productType": "LocalbootProduct",
							}
						],
					)

	with admin_service_config():
		with get_service_connection() as connection:
			with (
				tmp_client(connection, "client1.test.tld"),
				tmp_product(connection, "testproduct"),
			):
				cht = FakeInstallationThread(daemon=True)
				cht.start()
				cmd = [
					"messagebus",
					"wait-for-installation",
					"client1.test.tld",
					"testproduct",
					installation_status,
					"--timeout",
					"10",
				]
				exit_code, _stdout, _stderr = run_cli(cmd)
				cht.join()
				assert exit_code == 0 if success else 1


@pytest.mark.opsi_service
def test_wait_for_host() -> None:
	class FakeHostConnectionThread(Thread):
		def run(self) -> None:
			with log_context({"instance": "FakeHostConnectionThread"}):
				time.sleep(2)
				with get_host_service_client("client1.test.tld", "00000000000000000000000000000000") as client:
					client.connect_messagebus()

	with admin_service_config():
		with get_service_connection() as connection:
			with tmp_client(connection, "client1.test.tld", "00000000000000000000000000000000"):
				thread = FakeHostConnectionThread(daemon=True)
				thread.start()
				cmd = [
					"messagebus",
					"wait-for-host",
					"client1.test.tld",
					"--timeout",
					"10",
				]
				exit_code, _stdout, _stderr = run_cli(cmd)
				thread.join()
				assert exit_code == 0
