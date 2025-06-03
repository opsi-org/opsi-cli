# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_client_action
"""

import contextlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch

import pytest
from opsicommon.client.opsiservice import ServiceClient
from opsicommon.objects import ProductOnClient

from .utils import run_cli, tmp_client, tmp_host_group, tmp_product, tmp_product_group

sys.path.append(str(Path("./plugins/client-action").resolve()))
from python.client_action_worker import ClientActionArgs  # type: ignore[import-not-found]

CLIENT1 = "pytest-client1.test.tld"
CLIENT2 = "pytest-client2.test.tld"
CLIENT3 = "pytest-client3.test.tld"
PRODUCT1 = "pytest-product1"
PRODUCT2 = "pytest-product2"
PRODUCT3 = "pytest-product3"
PRODUCT4 = "pytest-product4"
H_GROUP1 = "pytest-test-host-group"
H_GROUP2 = "pytest-nested-host-group"
P_GROUP = "pytest-test-product-group"


def test_ClientActionArgs() -> None:
	args = ClientActionArgs()
	assert args.clients == set()
	assert args.client_groups == set()
	assert args.clients_from_depots == set()
	assert args.ip_addresses == set()
	assert args.exclude_clients == set()
	assert args.exclude_client_groups == set()
	assert args.exclude_ip_addresses == set()
	assert args.where_action_request == set()
	assert args.only_online is False

	args = ClientActionArgs(
		clients=" all, client2.opsi.test, client2.opsi.test",
		client_groups=" group1 , group2 ",
		clients_from_depots="depot1.opsi.test ,depot2.opsi.test ,depot2.opsi.test",
		ip_addresses="10.10.10.1,::1",
		exclude_clients="client1.opsi.test",
		exclude_client_groups="group4,group3, group4",
		exclude_ip_addresses="192.168.1.1, ::1",
		where_action_request="setup, uninstall",
		only_online=True,
	)
	assert args.clients == {"all", "client2.opsi.test"}
	assert args.client_groups == {"group1", "group2"}
	assert args.clients_from_depots == {"depot1.opsi.test", "depot2.opsi.test"}
	assert args.ip_addresses == {"10.10.10.1", "::1"}
	assert args.exclude_clients == {"client1.opsi.test"}
	assert args.exclude_client_groups == {"group3", "group4"}
	assert args.exclude_ip_addresses == {"192.168.1.1", "::1"}
	assert args.where_action_request == {"setup", "uninstall"}
	assert args.only_online is True

	with pytest.raises(ValueError):
		ClientActionArgs(clients="invalid_client")
	with pytest.raises(ValueError):
		ClientActionArgs(client_groups="invalid ; group")
	with pytest.raises(ValueError):
		ClientActionArgs(clients_from_depots="invalid ; depot")
	with pytest.raises(ValueError):
		ClientActionArgs(ip_addresses="invalid_ip")
	with pytest.raises(ValueError):
		ClientActionArgs(exclude_clients="invalid_client")
	with pytest.raises(ValueError):
		ClientActionArgs(exclude_client_groups="invalid ; group")
	with pytest.raises(ValueError):
		ClientActionArgs(exclude_ip_addresses="invalid_ip")
	with pytest.raises(ValueError):
		ClientActionArgs(where_action_request="invalid_request")


@pytest.mark.opsi_service
def test_set_action_request_single(admin_service_client: ServiceClient) -> None:
	with (
		tmp_client(admin_service_client, CLIENT1),
		tmp_client(admin_service_client, CLIENT2),
		tmp_product(admin_service_client, PRODUCT1),
		tmp_product(admin_service_client, PRODUCT2),
	):
		cmd = [
			"client-action",
			"--clients",
			f"{CLIENT1},{CLIENT2}",
			"set-action-request",
			"--products",
			f"{PRODUCT1},{PRODUCT2}",
		]

		exit_code, _stdout, _stderr = run_cli(cmd)
		assert exit_code == 0
		pocs = admin_service_client.jsonrpc(
			"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
		)
		assert len(pocs) == 4
		for poc in pocs:
			assert poc.actionRequest == "setup"

		cmd += ["--set-action-request", "none"]
		exit_code, _stdout, _stderr = run_cli(cmd)
		assert exit_code == 0
		pocs = admin_service_client.jsonrpc(
			"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
		)
		assert len(pocs) == 4
		for poc in pocs:
			assert poc.actionRequest in ("none", None)


@pytest.mark.opsi_service
def test_set_action_request_group(admin_service_client: ServiceClient) -> None:
	with (
		tmp_client(admin_service_client, CLIENT1),
		tmp_client(admin_service_client, CLIENT2),
		tmp_product(admin_service_client, PRODUCT1),
		tmp_product(admin_service_client, PRODUCT2),
	):
		with (
			tmp_host_group(admin_service_client, H_GROUP1, {CLIENT1, CLIENT2}),
			tmp_product_group(admin_service_client, P_GROUP, [PRODUCT1, PRODUCT2]),
		):
			cmd = ["client-action", "--client-groups", H_GROUP1, "set-action-request", "--product-groups", P_GROUP]

			exit_code, _stdout, _stderr = run_cli(cmd)
			assert exit_code == 0
			pocs = admin_service_client.jsonrpc(
				"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
			)
			assert len(pocs) == 4
			for poc in pocs:
				assert poc.actionRequest == "setup"

			cmd += ["--request-type", "none"]
			exit_code, _stdout, _stderr = run_cli(cmd)
			assert exit_code == 0
			pocs = admin_service_client.jsonrpc(
				"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
			)
			assert len(pocs) == 4
			for poc in pocs:
				assert poc.actionRequest in ("none", None)


@pytest.mark.opsi_service
@pytest.mark.parametrize(
	"selection, process, dry_run",
	(
		("failed", False, False),
		("outdated", False, False),
		("installed", False, False),
		("failed", True, False),
		("outdated", True, False),
		("installed", True, True),
	),
)
@pytest.mark.parametrize(
	"set_action_request, set_action_progress, set_action_result, set_installation_status",
	(
		(None, None, None, None),
		("setup", "installing", "successful", "not_installed"),
		("setup", "", "", "installed"),
	),
)
def test_set_action_request_where(
	admin_service_client: ServiceClient,
	selection: Literal["failed", "outdated", "installed"],
	process: bool,
	dry_run: bool,
	set_action_request: str | None,
	set_action_progress: str | None,
	set_action_result: str | None,
	set_installation_status: str | None,
) -> None:
	with (
		tmp_client(admin_service_client, CLIENT1),
		tmp_client(admin_service_client, CLIENT2),
		tmp_product(admin_service_client, PRODUCT1) as product1,
		tmp_product(admin_service_client, PRODUCT2) as product2,
		tmp_product(admin_service_client, PRODUCT3) as product3,
		tmp_product(admin_service_client, PRODUCT4) as product4,
	):
		# Create product on clients
		pocs: list[ProductOnClient] = [
			# product1 failed on client1
			ProductOnClient(
				clientId=CLIENT1,
				productId=product1.id,
				productType=product1.getType(),
				installationStatus="unknown",
				actionRequest="none",
				actionResult="failed",
			),
			# product2 outdated on client1
			ProductOnClient(
				clientId=CLIENT1,
				productId=product2.id,
				productType=product2.getType(),
				productVersion="0",
				packageVersion="0",
				installationStatus="installed",
				actionRequest="none",
				actionResult="",
			),
			# product3 installed on client1
			ProductOnClient(
				clientId=CLIENT1,
				productId=product3.id,
				productType=product3.getType(),
				installationStatus="installed",
				actionRequest="none",
				actionResult="",
			),
			# product4 installed and up-to-date, setup set on client1
			ProductOnClient(
				clientId=CLIENT1,
				productId=product4.id,
				productType=product4.getType(),
				productVersion=product4.productVersion,
				packageVersion=product4.packageVersion,
				installationStatus="installed",
				actionRequest="setup",
				actionResult="",
			),
			# product1 installed on client2
			ProductOnClient(
				clientId=CLIENT2,
				productId=product1.id,
				productType=product1.getType(),
				installationStatus="installed",
				actionRequest="none",
				actionResult="",
			),
			# product2 up-to-date on client2
			ProductOnClient(
				clientId=CLIENT2,
				productId=product2.id,
				productType=product2.getType(),
				productVersion=product2.productVersion,
				packageVersion=product2.packageVersion,
				installationStatus="installed",
				actionRequest="none",
				actionResult="",
			),
			# product3 not_installed on client2
			ProductOnClient(
				clientId=CLIENT2,
				productId=product3.id,
				productType=product3.getType(),
				installationStatus="not_installed",
				actionRequest="none",
				actionResult="",
			),
		]

		admin_service_client.jsonrpc("productOnClient_createObjects", params=[pocs])

		jsonrpc_orig = ServiceClient.jsonrpc
		rpcs: list[list[Any]] = []

		def mock_jsonrpc(
			self: ServiceClient,
			method: str,
			params: tuple[Any, ...] | list[Any] | dict[str, Any] | None = None,
			*,
			connect_timeout: float | None = None,
			read_timeout: float | None = None,
			return_result_only: bool = True,
			create_objects: bool | None = None,
			assert_connected: bool = True,
		) -> Any:
			nonlocal rpcs
			rpcs.append([method, params, connect_timeout, read_timeout, return_result_only, create_objects])
			if method == "hostControl_processActionRequests":
				return {}
			return jsonrpc_orig(
				self,
				method,
				params,
				connect_timeout=connect_timeout,
				read_timeout=read_timeout,
				return_result_only=return_result_only,
				create_objects=create_objects,
				assert_connected=assert_connected,
			)

		cmd = [
			"--output-format",
			"json",
			"client-action",
			"--clients",
			f"{CLIENT1},{CLIENT2}",
			"set-action-request",
			f"--where-{selection}",
			"--setup-on-action",
			PRODUCT3,
		]
		if set_action_request is not None:
			cmd += ["--set-action-request", set_action_request]
		if set_action_progress is not None:
			cmd += ["--set-action-progress", set_action_progress]
		if set_action_result is not None:
			cmd += ["--set-action-result", set_action_result]
		if set_installation_status is not None:
			cmd += ["--set-installation-status", set_installation_status]
		if process:
			cmd.append("--process")
		if dry_run:
			cmd.insert(0, "--dry-run")

		rpcs.clear()
		with patch("opsicommon.client.opsiservice.ServiceClient.jsonrpc", mock_jsonrpc):
			exit_code, stdout, stderr = run_cli(cmd)

		assert exit_code == 0

		pocs = sorted(
			admin_service_client.jsonrpc(
				"productOnClient_getObjects",
				params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2, PRODUCT3, PRODUCT4]}],
			),
			key=lambda poc: (poc.clientId, poc.productId),
		)

		assert len(pocs) == 7
		assert pocs[0].clientId == CLIENT1
		assert pocs[0].productId == PRODUCT1
		assert pocs[1].clientId == CLIENT1
		assert pocs[1].productId == PRODUCT2
		assert pocs[2].clientId == CLIENT1
		assert pocs[2].productId == PRODUCT3
		assert pocs[3].clientId == CLIENT1
		assert pocs[3].productId == PRODUCT4
		assert pocs[4].clientId == CLIENT2
		assert pocs[4].productId == PRODUCT1
		assert pocs[5].clientId == CLIENT2
		assert pocs[5].productId == PRODUCT2
		assert pocs[6].clientId == CLIENT2
		assert pocs[6].productId == PRODUCT3

		expected_actions = {client_id: {PRODUCT1: "none", PRODUCT2: "none", PRODUCT3: "none"} for client_id in (CLIENT1, CLIENT2)}
		expected_actions[CLIENT1][PRODUCT4] = "none"

		if selection == "failed":
			expected_actions[CLIENT1][PRODUCT1] = "setup"  # failed => setup
			expected_actions[CLIENT1][PRODUCT3] = "setup"  # setup-on-action
		elif selection == "outdated":
			expected_actions[CLIENT1][PRODUCT2] = "setup"  # outdated => setup
			expected_actions[CLIENT1][PRODUCT3] = "setup"  # outdated => setup (no version info) and setup-on-action
			expected_actions[CLIENT2][PRODUCT1] = "setup"  # outdated => setup (no version info)
			expected_actions[CLIENT2][PRODUCT3] = "setup"  # setup-on-action
		elif selection == "installed":
			expected_actions[CLIENT1][PRODUCT2] = "setup"  # installed => setup
			expected_actions[CLIENT1][PRODUCT3] = "setup"  # setup-on-action
			expected_actions[CLIENT1][PRODUCT4] = "setup"  # installed => setup
			expected_actions[CLIENT2][PRODUCT1] = "setup"  # installed => setup
			expected_actions[CLIENT2][PRODUCT2] = "setup"  # installed => setup
			expected_actions[CLIENT2][PRODUCT3] = "setup"  # setup-on-action

		assert pocs[0].actionRequest == ("none" if dry_run else expected_actions[CLIENT1][PRODUCT1])
		assert pocs[1].actionRequest == ("none" if dry_run else expected_actions[CLIENT1][PRODUCT2])
		assert pocs[2].actionRequest == ("none" if dry_run else expected_actions[CLIENT1][PRODUCT3])
		assert pocs[3].actionRequest == "setup"  # actionRequest was "setup" before
		assert pocs[4].actionRequest == ("none" if dry_run else expected_actions[CLIENT2][PRODUCT1])
		assert pocs[5].actionRequest == ("none" if dry_run else expected_actions[CLIENT2][PRODUCT2])
		assert pocs[6].actionRequest == ("none" if dry_run else expected_actions[CLIENT2][PRODUCT3])

		if not dry_run:
			for poc in pocs:
				if expected_actions[poc.clientId][poc.productId] not in ("none", None):
					if set_action_progress is not None:
						assert poc.actionProgress == set_action_progress
					if set_action_result is not None:
						assert poc.actionResult or "none" == set_action_result or "none"
					if set_installation_status is not None:
						assert poc.installationStatus == set_installation_status

		if process:
			unprocessed_actions = expected_actions.copy()
			for rpc in rpcs:
				if rpc[0] == "hostControl_processActionRequests":
					if dry_run:
						raise RuntimeError("Unexpected call to hostControl_processActionRequests on dry-run")

					client_id = rpc[1][0][0]
					product_ids = rpc[1][1]
					# print(f"process: {client_id}: {product_ids}")
					assert sorted(product_ids) == sorted(
						pid for pid, act in unprocessed_actions.pop(client_id, {}).items() if act == "setup"
					)
			if not dry_run:
				for client_id, actions in unprocessed_actions.items():
					assert all(act == "none" for act in actions.values())

		stderr = stderr.replace("\n", " ")
		if dry_run:
			if process:
				assert stderr.startswith("Action requests would have been set and processing would have been started. Here are the updated")
			else:
				assert stderr.startswith("Action requests would have been set. Here are the updated")
		else:
			if process:
				assert stderr.startswith("Action requests have been set and processing was started. Here are the updated")
			else:
				assert stderr.startswith("Action requests have been set. Here are the updated")

		expected_data = []
		for client_id, actions in expected_actions.items():
			for product_id, action in actions.items():
				if action == "setup":
					expected_data.append(
						{
							"clientId": client_id,
							"productId": product_id,
							"actionRequest": action,
						}
					)
		data = json.loads(stdout)
		assert len(expected_data) == len(data)


@pytest.mark.opsi_service
@pytest.mark.parametrize(
	"where_action_request,  expected_client_ids",
	(
		("setup", {CLIENT1, CLIENT2}),
		("uninstall", {CLIENT2}),
		("always", {CLIENT1}),
		("setup, uninstall", {CLIENT1, CLIENT2}),
		("always, once, always", {CLIENT1}),
	),
)
def test_where_action_request(admin_service_client: ServiceClient, where_action_request: str, expected_client_ids: set[str]) -> None:
	with (
		tmp_client(admin_service_client, CLIENT1),
		tmp_client(admin_service_client, CLIENT2),
		tmp_product(admin_service_client, PRODUCT1) as product1,
		tmp_product(admin_service_client, PRODUCT2) as product2,
		tmp_product(admin_service_client, PRODUCT3) as product3,
		tmp_product(admin_service_client, PRODUCT4) as product4,
	):
		# Create product on clients
		pocs: list[ProductOnClient] = [
			# product1 once on client1
			ProductOnClient(
				clientId=CLIENT1,
				productId=product1.id,
				productType=product1.getType(),
				actionRequest="once",
			),
			# product2 setup on client1
			ProductOnClient(
				clientId=CLIENT1,
				productId=product2.id,
				productType=product2.getType(),
				actionRequest="setup",
			),
			# product3 always on client1
			ProductOnClient(
				clientId=CLIENT1,
				productId=product3.id,
				productType=product3.getType(),
				actionRequest="always",
			),
			# product1 setup on client2
			ProductOnClient(
				clientId=CLIENT2,
				productId=product1.id,
				productType=product1.getType(),
				actionRequest="setup",
			),
			# product4 uninstall on client2
			ProductOnClient(
				clientId=CLIENT2,
				productId=product4.id,
				productType=product4.getType(),
				actionRequest="uninstall",
			),
		]

		admin_service_client.jsonrpc("productOnClient_createObjects", params=[pocs])

		cmd = [
			"--output-format",
			"json",
			"client-action",
			"--clients",
			"all",
			"--where-action-request",
			where_action_request,
			"set-action-request",
			"--products",
			PRODUCT1,
			"--set-action-request",
			"setup",
		]
		exit_code, stdout, stderr = run_cli(cmd)
		assert exit_code == 0

		data = json.loads(stdout)
		print(data)
		client_ids = {item["clientId"] for item in data}
		assert client_ids == expected_client_ids


@pytest.mark.opsi_service
def test_set_action_request_excludes(admin_service_client: ServiceClient) -> None:
	with (
		tmp_client(admin_service_client, CLIENT1),
		tmp_client(admin_service_client, CLIENT2),
		tmp_product(admin_service_client, PRODUCT1),
		tmp_product(admin_service_client, PRODUCT2),
		tmp_host_group(admin_service_client, H_GROUP1, {CLIENT2}),
		tmp_product_group(admin_service_client, P_GROUP, [PRODUCT2]),
	):
		cmd = [
			"client-action",
			f"--clients={CLIENT1},{CLIENT2}",
			"--exclude-clients=nonexistent.test.tld",
			f"--exclude-client-groups={H_GROUP1}",
			"set-action-request",
			f"--products={PRODUCT1},{PRODUCT2}",
			"--exclude-products=nonexistent",
			f"--exclude-product-groups={P_GROUP}",
		]

		exit_code, stdout, _stderr = run_cli(cmd)
		print(stdout)
		assert exit_code == 0
		pocs = admin_service_client.jsonrpc(
			"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
		)
		for poc in pocs:
			if poc.clientId == CLIENT1 and poc.productId == PRODUCT1:
				assert poc.actionRequest == "setup"
			else:
				assert poc.actionRequest in (None, "none")

		cmd += ["--request-type", "none"]
		exit_code, _stdout, _stderr = run_cli(cmd)
		assert exit_code == 0
		pocs = admin_service_client.jsonrpc(
			"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
		)
		for poc in pocs:
			assert poc.actionRequest in ("none", None)


@pytest.mark.opsi_service
def test_set_action_request_unknown_type(admin_service_client: ServiceClient) -> None:
	with tmp_client(admin_service_client, CLIENT1), tmp_product(admin_service_client, PRODUCT1):
		cmd = ["client-action", "--clients", CLIENT1, "set-action-request", "--products", PRODUCT1, "--set-action-request", "nonexistent"]
		exit_code, _stdout, _stderr = run_cli(cmd)
		assert exit_code == 1
		assert "Bad action request: 'nonexistent'" in _stderr


@pytest.mark.opsi_service
def test_set_action_request_only_online(admin_service_client: ServiceClient) -> None:
	with tmp_client(admin_service_client, CLIENT1), tmp_product(admin_service_client, PRODUCT1):
		cmd = ["client-action", "--clients", CLIENT1, "--only-online", "set-action-request", "--products", PRODUCT1]
		exit_code, _stdout, _stderr = run_cli(cmd)
		assert exit_code == 1
		pocs = admin_service_client.jsonrpc("productOnClient_getObjects", params=[[], {"clientId": CLIENT1, "productId": PRODUCT1}])
		assert len(pocs) == 0


@pytest.mark.opsi_service
def test_set_action_request_clients_from_depot(admin_service_client: ServiceClient) -> None:
	configserver = admin_service_client.jsonrpc("host_getObjects", params=[[], {"type": "OpsiConfigserver"}])[0].id
	with tmp_client(admin_service_client, CLIENT1), tmp_product(admin_service_client, PRODUCT1):
		cmd = ["client-action", "--clients-from-depots", configserver, "set-action-request", "--products", PRODUCT1]
		exit_code, _stdout, _stderr = run_cli(cmd)
		assert exit_code == 0
		pocs = admin_service_client.jsonrpc("productOnClient_getObjects", params=[[], {"clientId": CLIENT1, "productId": PRODUCT1}])
		assert len(pocs) == 1
		assert pocs[0].actionRequest == "setup"
		assert pocs[0].productId == PRODUCT1
		assert pocs[0].clientId == CLIENT1


@pytest.mark.opsi_service
def test_nested_groups_client_selection(admin_service_client: ServiceClient) -> None:
	with (
		tmp_client(admin_service_client, CLIENT1),
		tmp_client(admin_service_client, CLIENT2),
		tmp_product(admin_service_client, PRODUCT1),
		tmp_host_group(admin_service_client, H_GROUP1, {CLIENT1}),
		tmp_host_group(admin_service_client, H_GROUP2, {CLIENT2}, parent=H_GROUP1),
	):
		cmd = ["client-action", "--client-groups", H_GROUP1, "set-action-request", "--products", PRODUCT1]
		exit_code, _stdout, _stderr = run_cli(cmd)
		assert exit_code == 0
		print(admin_service_client.jsonrpc("group_getObjects", params=[[], {"id": [H_GROUP2]}]))
		print(admin_service_client.jsonrpc("objectToGroup_getObjects", params=[[], {"objectId": [CLIENT1, CLIENT2]}]))
		pocs = admin_service_client.jsonrpc(
			"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1]}]
		)
		print(pocs)
		assert len(pocs) == 2


@pytest.mark.opsi_service
def test_trigger_event(admin_service_client: ServiceClient) -> None:
	with tmp_client(admin_service_client, CLIENT1):
		cmd = ["client-action", "--clients", CLIENT1, "trigger-event", "--wakeup", "--wakeup-timeout", "0.5"]
		exit_code, _stdout, _stderr = run_cli(cmd)
		assert exit_code == 1  # No way to actually trigger an event or wake up a client


@pytest.mark.parametrize(
	"opsiscript_content", ('[Actions]\\nMessage \\"Hello, World!\\"\\nMessage \\"This is a multi-line opsi script.\\"', "setup.opsiscript")
)
@pytest.mark.opsi_service
def test_execute_opsiscript(admin_service_client: ServiceClient, tmp_path: Path, opsiscript_content: str) -> None:
	test_exception = Exception("Test exception")
	test_error = RuntimeError("Test error")
	highest_exit_code = 2
	(tmp_path / "setup.opsiscript").write_text(
		'[Actions]\\nMessage \\"Hello, World!\\"\\nMessage \\"This is a multi-line opsi script.\\"', encoding="utf-8"
	)
	mock_results = {
		f"host:{CLIENT1}": test_exception,
		f"host:{CLIENT2}": {
			"exit_code": highest_exit_code,
			"stdout": "",
			"stderr": test_error,
			"log_content": "[1] Essential log message\n[2] Critical log message\n[3] Error log message\n[4] Warning log message\n[5] Notice log message\n[6] Info log message\n[7] Debug log message\n[8] Trace log message\n[9] Secret log message",
		},
		f"host:{CLIENT3}": {
			"exit_code": 0,
			"stdout": "Hello, World!\nThis is a multi-line opsi script.",
			"stderr": "",
			"log_content": "[1] Essential log message\n[2] Critical log message\n[3] Error log message\n[4] Warning log message\n[5] Notice log message\n[6] Info log message\n[7] Debug log message\n[8] Trace log message\n[9] Secret log message",
		},
	}

	with patch("opsicli.messagebus.JSONRPCMessagebusConnection.jsonrpc", return_value=mock_results):
		with (
			tmp_client(admin_service_client, CLIENT1),
			tmp_client(admin_service_client, CLIENT2),
			tmp_client(admin_service_client, CLIENT3),
			contextlib.chdir(tmp_path),
		):
			cmd = [
				"--no-color",
				"client-action",
				"--clients",
				f"{CLIENT1},{CLIENT2},{CLIENT3}",
				"execute",
				"--opsi-script",
				opsiscript_content,
				"--opsi-script-log-level",
				str(6),
			]
			exit_code, _stdout, _stderr = run_cli(cmd)
			assert exit_code == highest_exit_code

			expected_output_pattern = (
				rf"\n─+ {CLIENT1} ─+\n"
				rf"{CLIENT1} \| {re.escape(str(test_exception))}\n\n"
				rf"─+ {CLIENT2} ─+\n"
				rf"{CLIENT2} \| EXIT CODE: {highest_exit_code}\n\n"
				rf"{CLIENT2} \| LOG:\n"
				rf"{CLIENT2} \| \[1\] Essential log message\n"
				rf"{CLIENT2} \| \[2\] Critical log message\n"
				rf"{CLIENT2} \| \[3\] Error log message\n"
				rf"{CLIENT2} \| \[4\] Warning log message\n"
				rf"{CLIENT2} \| \[5\] Notice log message\n"
				rf"{CLIENT2} \| \[6\] Info log message\n\n"
				rf"{CLIENT2} \| STDERR:\n"
				rf"{CLIENT2} \| {re.escape(str(test_error))}\n\n"
				rf"─+ {CLIENT3} ─+\n"
				rf"{CLIENT3} \| EXIT CODE: 0\n\n"
				rf"{CLIENT3} \| STDOUT:\n"
				rf"{CLIENT3} \| Hello, World!\n"
				rf"{CLIENT3} \| This is a multi-line opsi script.\n\n"
				rf"{CLIENT3} \| LOG:\n"
				rf"{CLIENT3} \| \[1\] Essential log message\n"
				rf"{CLIENT3} \| \[2\] Critical log message\n"
				rf"{CLIENT3} \| \[3\] Error log message\n"
				rf"{CLIENT3} \| \[4\] Warning log message\n"
				rf"{CLIENT3} \| \[5\] Notice log message\n"
				rf"{CLIENT3} \| \[6\] Info log message\n"
			)
			assert re.fullmatch(expected_output_pattern, _stdout)
			assert _stderr == ""
