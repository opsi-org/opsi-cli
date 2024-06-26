"""
test_client_action
"""

import pytest
from opsicommon.objects import ProductOnClient

from opsicli.opsiservice import get_service_connection

from .utils import (
	container_connection,
	run_cli,
	tmp_client,
	tmp_host_group,
	tmp_product,
	tmp_product_group,
)

CLIENT1 = "pytest-client1.test.tld"
CLIENT2 = "pytest-client2.test.tld"
PRODUCT1 = "pytest-product1"
PRODUCT2 = "pytest-product2"
H_GROUP1 = "pytest-test-host-group"
H_GROUP2 = "pytest-nested-host-group"
P_GROUP = "pytest-test-product-group"


@pytest.mark.requires_testcontainer
def test_set_action_request_single() -> None:
	with container_connection():
		connection = get_service_connection()
		with (
			tmp_client(connection, CLIENT1),
			tmp_client(connection, CLIENT2),
			tmp_product(connection, PRODUCT1),
			tmp_product(connection, PRODUCT2),
		):
			cmd = ["client-action", "--clients", f"{CLIENT1},{CLIENT2}", "set-action-request", "--products", f"{PRODUCT1},{PRODUCT2}"]

			exit_code, _stdout, _stderr = run_cli(cmd)
			assert exit_code == 0
			pocs = connection.jsonrpc(
				"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
			)
			assert len(pocs) == 4
			for poc in pocs:
				assert poc.actionRequest == "setup"

			cmd += ["--request-type", "none"]
			exit_code, _stdout, _stderr = run_cli(cmd)
			assert exit_code == 0
			pocs = connection.jsonrpc(
				"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
			)
			assert len(pocs) == 4
			for poc in pocs:
				assert poc.actionRequest in ("none", None)


@pytest.mark.requires_testcontainer
def test_set_action_request_group() -> None:
	with container_connection():
		connection = get_service_connection()
		with (
			tmp_client(connection, CLIENT1),
			tmp_client(connection, CLIENT2),
			tmp_product(connection, PRODUCT1),
			tmp_product(connection, PRODUCT2),
		):
			with tmp_host_group(connection, H_GROUP1, {CLIENT1, CLIENT2}), tmp_product_group(connection, P_GROUP, [PRODUCT1, PRODUCT2]):
				cmd = ["-l6", "client-action", "--client-groups", H_GROUP1, "set-action-request", "--product-groups", P_GROUP]

				exit_code, _stdout, _stderr = run_cli(cmd)
				assert exit_code == 0
				pocs = connection.jsonrpc(
					"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
				)
				assert len(pocs) == 4
				for poc in pocs:
					assert poc.actionRequest == "setup"

				cmd += ["--request-type", "none"]
				exit_code, _stdout, _stderr = run_cli(cmd)
				assert exit_code == 0
				pocs = connection.jsonrpc(
					"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
				)
				assert len(pocs) == 4
				for poc in pocs:
					assert poc.actionRequest in ("none", None)


@pytest.mark.requires_testcontainer
def test_set_action_request_where_failed() -> None:
	with container_connection():
		connection = get_service_connection()
		with tmp_client(connection, CLIENT1), tmp_product(connection, PRODUCT1), tmp_product(connection, PRODUCT2):
			# create a failed POC
			connection.jsonrpc(
				"productOnClient_updateObjects",
				params=[
					ProductOnClient(
						clientId=CLIENT1,
						productId=PRODUCT1,
						productType="LocalbootProduct",
						actionResult="failed",
						actionRequest=None,
					),
				],
			)

			exit_code, _stdout, _stderr = run_cli(
				["client-action", "--clients", CLIENT1, "set-action-request", "--where-failed", "--setup-on-action", PRODUCT2]
			)
			assert exit_code == 0
			pocs = connection.jsonrpc("productOnClient_getObjects", params=[[], {"clientId": CLIENT1, "productId": [PRODUCT1, PRODUCT2]}])
			assert len(pocs) == 2
			for poc in pocs:
				assert poc.actionRequest == "setup"


@pytest.mark.requires_testcontainer
def test_set_action_request_excludes() -> None:
	with container_connection():
		connection = get_service_connection()
		with (
			tmp_client(connection, CLIENT1),
			tmp_client(connection, CLIENT2),
			tmp_product(connection, PRODUCT1),
			tmp_product(connection, PRODUCT2),
			tmp_host_group(connection, H_GROUP1, {CLIENT2}),
			tmp_product_group(connection, P_GROUP, [PRODUCT2]),
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
			pocs = connection.jsonrpc(
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
			pocs = connection.jsonrpc(
				"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
			)
			for poc in pocs:
				assert poc.actionRequest in ("none", None)


@pytest.mark.requires_testcontainer
def test_set_action_request_unknown_type() -> None:
	with container_connection():
		connection = get_service_connection()
		with tmp_client(connection, CLIENT1), tmp_product(connection, PRODUCT1):
			cmd = ["client-action", "--clients", CLIENT1, "set-action-request", "--products", PRODUCT1, "--request-type", "nonexistent"]
			exit_code, _stdout, _stderr = run_cli(cmd)
			assert exit_code == 0
			pocs = connection.jsonrpc("productOnClient_getObjects", params=[[], {"clientId": CLIENT1, "productId": PRODUCT1}])
			assert len(pocs) == 0


@pytest.mark.requires_testcontainer
def test_set_action_request_only_online() -> None:
	with container_connection():
		connection = get_service_connection()
		with tmp_client(connection, CLIENT1), tmp_product(connection, PRODUCT1):
			cmd = ["client-action", "--clients", CLIENT1, "--only-online", "set-action-request", "--products", PRODUCT1]
			exit_code, _stdout, _stderr = run_cli(cmd)
			assert exit_code == 1
			pocs = connection.jsonrpc("productOnClient_getObjects", params=[[], {"clientId": CLIENT1, "productId": PRODUCT1}])
			assert len(pocs) == 0


@pytest.mark.requires_testcontainer
def test_set_action_request_clients_from_depot() -> None:
	with container_connection():
		connection = get_service_connection()
		configserver = connection.jsonrpc("host_getObjects", params=[[], {"type": "OpsiConfigserver"}])[0].id
		with tmp_client(connection, CLIENT1), tmp_product(connection, PRODUCT1):
			cmd = ["client-action", "--clients-from-depots", configserver, "set-action-request", "--products", PRODUCT1]
			exit_code, _stdout, _stderr = run_cli(cmd)
			assert exit_code == 0
			pocs = connection.jsonrpc("productOnClient_getObjects", params=[[], {"clientId": CLIENT1, "productId": PRODUCT1}])
			assert len(pocs) == 1
			assert pocs[0].actionRequest == "setup"
			assert pocs[0].productId == PRODUCT1
			assert pocs[0].clientId == CLIENT1


@pytest.mark.requires_testcontainer
def test_nested_groups_client_selection() -> None:
	with container_connection():
		connection = get_service_connection()
		with (
			tmp_client(connection, CLIENT1),
			tmp_client(connection, CLIENT2),
			tmp_product(connection, PRODUCT1),
			tmp_host_group(connection, H_GROUP1, {CLIENT1}),
			tmp_host_group(connection, H_GROUP2, {CLIENT2}, parent=H_GROUP1),
		):
			cmd = ["client-action", "--client-groups", H_GROUP1, "set-action-request", "--products", PRODUCT1]
			exit_code, _stdout, _stderr = run_cli(cmd)
			assert exit_code == 0
			print(connection.jsonrpc("group_getObjects", params=[[], {"id": [H_GROUP2]}]))
			print(connection.jsonrpc("objectToGroup_getObjects", params=[[], {"objectId": [CLIENT1, CLIENT2]}]))
			pocs = connection.jsonrpc("productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1]}])
			print(pocs)
			assert len(pocs) == 2


@pytest.mark.requires_testcontainer
def test_trigger_event() -> None:
	with container_connection():
		connection = get_service_connection()
		with tmp_client(connection, CLIENT1):
			cmd = ["client-action", "--clients", CLIENT1, "trigger-event", "--wakeup", "--wakeup-timeout", "0.5"]
			exit_code, _stdout, _stderr = run_cli(cmd)
			assert exit_code == 0  # No way to actually trigger an event or wake up a client
