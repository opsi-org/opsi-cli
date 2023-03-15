"""
test_client_action
"""

import pytest
from opsicommon.objects import ProductOnClient

from .utils import container_connection, run_cli

CLIENT1 = "pytest-client1.test.tld"
CLIENT2 = "pytest-client2.test.tld"
PRODUCT1 = "hwaudit"
PRODUCT2 = "swaudit"
H_GROUP = "pytest-test-client-group"
P_GROUP = "pytest-test-product-group"


@pytest.mark.requires_testcontainer
def test_set_action_request_single() -> None:
	with container_connection() as connection:
		connection.jsonrpc("host_createOpsiClient", params=[CLIENT1])
		connection.jsonrpc("host_createOpsiClient", params=[CLIENT2])
		cmd = ["client-action", "--clients", f"{CLIENT1},{CLIENT2}", "set-action-request", "--products", f"{PRODUCT1},{PRODUCT2}"]

		(code, _) = run_cli(cmd)
		assert code == 0
		poc = connection.jsonrpc(
			"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
		)
		for index in range(4):
			assert poc[index].get("actionRequest") == "setup"

		cmd += ["--request-type", "none"]
		(code, _) = run_cli(cmd)
		assert code == 0
		poc = connection.jsonrpc(
			"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
		)
		for index in range(4):
			assert poc[index].get("actionRequest") in ("none", None)

		connection.jsonrpc("host_delete", params=[CLIENT1])
		connection.jsonrpc("host_delete", params=[CLIENT2])


@pytest.mark.requires_testcontainer
def test_set_action_request_group() -> None:
	with container_connection() as connection:
		connection.jsonrpc("host_createOpsiClient", params=[CLIENT1])
		connection.jsonrpc("host_createOpsiClient", params=[CLIENT2])
		connection.jsonrpc("group_createHostGroup", params=[H_GROUP])
		connection.jsonrpc("objectToGroup_create", params=["HostGroup", H_GROUP, CLIENT1])
		connection.jsonrpc("objectToGroup_create", params=["HostGroup", H_GROUP, CLIENT2])
		connection.jsonrpc("group_createObjects", params=[{"id": P_GROUP, "type": "ProductGroup"}])
		connection.jsonrpc("objectToGroup_create", params=["ProductGroup", P_GROUP, PRODUCT1])
		connection.jsonrpc("objectToGroup_create", params=["ProductGroup", P_GROUP, PRODUCT2])
		cmd = ["client-action", "--client-groups", H_GROUP, "set-action-request", "--product-groups", P_GROUP]

		(code, _) = run_cli(cmd)
		assert code == 0
		poc = connection.jsonrpc(
			"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
		)
		for index in range(4):
			assert poc[index].get("actionRequest") == "setup"

		cmd += ["--request-type", "none"]
		(code, _) = run_cli(cmd)
		assert code == 0
		poc = connection.jsonrpc(
			"productOnClient_getObjects", params=[[], {"clientId": [CLIENT1, CLIENT2], "productId": [PRODUCT1, PRODUCT2]}]
		)
		for index in range(4):
			assert poc[index].get("actionRequest") in ("none", None)

		connection.jsonrpc("group_deleteObjects", params=[{"id": H_GROUP}])
		connection.jsonrpc("group_deleteObjects", params=[{"id": P_GROUP}])
		connection.jsonrpc("host_delete", params=[CLIENT1])
		connection.jsonrpc("host_delete", params=[CLIENT2])


@pytest.mark.requires_testcontainer
def test_set_action_request_where_failed() -> None:
	with container_connection() as connection:
		connection.jsonrpc("host_createOpsiClient", params=[CLIENT1])
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

		(code, _) = run_cli(["client-action", "--clients", CLIENT1, "set-action-request", "--where-failed", "--setup-on-action", PRODUCT2])
		assert code == 0
		poc = connection.jsonrpc("productOnClient_getObjects", params=[[], {"clientId": CLIENT1, "productId": [PRODUCT1, PRODUCT2]}])
		for index in range(2):
			assert poc[index].get("actionRequest") == "setup"

		connection.jsonrpc("host_delete", params=[CLIENT1])
