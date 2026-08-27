# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from opsi.opsi.service.client import ServiceClient

from plugins.datastore.python.product_client_state import list_product_client_state
from tests.utils import get_depot_id, run_cli, stdout_into_list, tmp_client, tmp_product

CLIENT_ID_1 = "pytest-client1.test.tld"
CLIENT_ID_2 = "pytest-client2.test.tld"

PRODUCT_ID_1 = "pytest-product1"
PRODUCT_ID_2 = "pytest-product2"

# ===============
# HELP FUNCTIONS
# ===============


# get products from depot and setting locked to 'True' manually
# update depot with locked products
def _lock_products_manually(admin_service_client: ServiceClient, product_id: str | None = None) -> None:
	products = admin_service_client.productOnDepot_getObjects(productId=product_id or [])  # ty: ignore[unresolved-attribute]
	for product in products:
		product.locked = True
	admin_service_client.productOnDepot_updateObjects(products)  # ty: ignore[unresolved-attribute]


# unlock products with given product-id and depot-id
def _unlock_products_with_cli(filter: list[str], expected_output: list[str] | None = None, expected_error: list[str] | None = None) -> None:
	args = ["datastore", "product", "unlock"] + filter

	exit_code, _stdout, _stderr = run_cli(args)

	if expected_output:
		assert exit_code == 0
		for expect in expected_output:
			assert expect in _stdout
	elif expected_error:
		assert exit_code != 0
		for err in expected_error:
			assert err in _stderr
	else:
		assert exit_code == 0


# verify the given locked status (e.g. is product.locked = True or False?)
def _verify_lock_status(admin_service_client: ServiceClient, is_locked: bool, product_id: str | None = None) -> None:
	products = admin_service_client.productOnDepot_getObjects(productId=product_id or [])  # ty: ignore[unresolved-attribute]
	for prod in products:
		assert prod.locked is is_locked


# install broken package -> failed installation
def _lock_products_by_installing_broken_package() -> None:
	package_name = "gimp2_broken_1.0-1.opsi"
	broken_package = Path(f"tests/test_data/plugins/package/{package_name}")
	run_cli(["package", "install", str(broken_package)])


# =========
# PYTESTS
# =========


# ===================================(PRODUCT UNLOCK || TESTS)============================================
# Locking the products -> verify the lock status -> unlock products with cli -> verify lock status again


class TestProductUnlock:
	# unlock single product
	@staticmethod
	@pytest.mark.opsi_service
	def test_unlock_single_product(admin_service_client: ServiceClient) -> None:
		with tmp_product(admin_service_client, PRODUCT_ID_1):
			_lock_products_manually(admin_service_client, product_id=PRODUCT_ID_1)
			_verify_lock_status(admin_service_client, is_locked=True)
			_unlock_products_with_cli(
				filter=["--where", f"productId={PRODUCT_ID_1}"],
				expected_output=[PRODUCT_ID_1],
			)
			_verify_lock_status(admin_service_client, is_locked=False)

	# unlock multiple products
	@staticmethod
	@pytest.mark.opsi_service
	def test_unlock_multiple_products(admin_service_client: ServiceClient) -> None:
		with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
			_lock_products_manually(admin_service_client)
			_verify_lock_status(admin_service_client, is_locked=True)
			_unlock_products_with_cli(
				filter=["--where", f"productId={PRODUCT_ID_1}", "--where", f"productId={PRODUCT_ID_2}"],
				expected_output=[PRODUCT_ID_1, PRODUCT_ID_2],
			)
			_verify_lock_status(admin_service_client, is_locked=False)

	# unlock products after failed package installation
	@staticmethod
	@pytest.mark.opsi_service
	def test_unlock_after_failed_installation(admin_service_client: ServiceClient) -> None:
		with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
			_lock_products_by_installing_broken_package()
			_verify_lock_status(
				admin_service_client,
				is_locked=True,
				product_id="gimp2",
			)
			_unlock_products_with_cli(
				filter=["--where", "productId=gimp2"],
				expected_output=["gimp2"],
			)
			_verify_lock_status(admin_service_client, is_locked=False, product_id="gimp2")

	# test wrong depotId
	@staticmethod
	@pytest.mark.opsi_service
	def test_wrong_depot_id(admin_service_client: ServiceClient) -> None:
		_unlock_products_with_cli(
			filter=["--where", "depotId=hello,test", "--where", "productId=*"],
			expected_error=[
				"Invalid value in filter condition",
				"The specified",
				"was not found",
				"Please use one or multiple",
				"available depotId's",
				f"{get_depot_id(admin_service_client)}",
			],
		)

	# wrong product_id
	@staticmethod
	@pytest.mark.opsi_service
	def test_wrong_product_id() -> None:
		_unlock_products_with_cli(
			filter=["--where", "productId=non-existent-product-123"], expected_error=["No products found matching the filtering criteria."]
		)

	# test if product unlock defaults correctly when no depotId is given
	@staticmethod
	@pytest.mark.opsi_service
	def test_no_depot_id(admin_service_client: ServiceClient) -> None:
		with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
			_lock_products_manually(admin_service_client)
			_verify_lock_status(admin_service_client, is_locked=True)
			_unlock_products_with_cli(
				filter=["--where", f"productId={PRODUCT_ID_1}", "--where", f"productId={PRODUCT_ID_2}"],
				expected_output=[PRODUCT_ID_1, PRODUCT_ID_2],
			)
			_verify_lock_status(admin_service_client, is_locked=False)

	# test --all flag
	@staticmethod
	@pytest.mark.opsi_service
	def test_all_flag(admin_service_client: ServiceClient) -> None:
		with (
			tmp_product(admin_service_client, PRODUCT_ID_1),
			tmp_product(admin_service_client, PRODUCT_ID_2),
		):
			_lock_products_manually(admin_service_client)
			_verify_lock_status(admin_service_client, is_locked=True)
			_unlock_products_with_cli(
				filter=["--all"],
				expected_output=[PRODUCT_ID_1, PRODUCT_ID_2],
			)
			_verify_lock_status(admin_service_client, is_locked=False)

	# test unlocking unlocked product
	@staticmethod
	@pytest.mark.opsi_service
	def test_unlock_already_unlocked(admin_service_client: ServiceClient) -> None:
		with tmp_product(admin_service_client, PRODUCT_ID_1):
			_verify_lock_status(admin_service_client, is_locked=False, product_id=PRODUCT_ID_1)
			_unlock_products_with_cli(
				filter=["--where", f"productId={PRODUCT_ID_1}"],
				expected_output=[PRODUCT_ID_1],
			)
			_verify_lock_status(admin_service_client, is_locked=False, product_id=PRODUCT_ID_1)

	# dry run:  no products should be unlocked
	@staticmethod
	@pytest.mark.opsi_service
	def test_unlock_dry_run(admin_service_client: ServiceClient, capsys) -> None:
		with tmp_product(admin_service_client, PRODUCT_ID_1):
			_lock_products_manually(admin_service_client, product_id=PRODUCT_ID_1)
			args = ["--dry-run", "datastore", "product", "unlock", "--where", f"productId={PRODUCT_ID_1}"]
			exit_code, _stdout, _stderr = run_cli(args)

			assert exit_code == 0
			assert "Unlocking products skipped due to dry run" in _stderr
			assert PRODUCT_ID_1 in _stdout
			_verify_lock_status(admin_service_client, is_locked=True, product_id=PRODUCT_ID_1)

	# no products on depot
	@staticmethod
	@pytest.mark.opsi_service
	def test_unlock_on_empty_system(admin_service_client: ServiceClient) -> None:
		_unlock_products_with_cli(
			filter=["--where", "productId=non-existent-product"],
			expected_error=["No products found matching the filtering criteria."],
		)


# ===================================(PRODUCT-CLIENT-STATE LIST || TESTS)============================================
def test_list_product_client_state_nonexistent_client() -> None:
	service_client = MagicMock()
	service_client.host_getIdents.return_value = []

	with patch("plugins.datastore.python.product_client_state.get_service_connection", return_value=service_client):
		with pytest.raises(ValueError, match="No clients found matching the supplied clientId filter: nonexistent.test.invalid"):
			list_product_client_state.callback(("clientId=nonexistent.test.invalid",), False)  # ty: ignore[call-non-callable]

	service_client.productOnDepot_getIdents.assert_not_called()
	service_client.productOnClient_getObjects.assert_not_called()


@pytest.mark.opsi_service
def test_list_product_client_state_without_depot_mapping_skips_depot_products() -> None:
	service_client = MagicMock()
	service_client.host_getIdents.return_value = [CLIENT_ID_1]
	service_client.configState_getClientToDepotserver.return_value = []
	service_client.productOnClient_getObjects.return_value = []

	with patch("plugins.datastore.python.product_client_state.get_service_connection", return_value=service_client):
		exit_code, _stdout, stderr = run_cli(["datastore", "product-client-state", "list", "--where", f"clientId={CLIENT_ID_1}"])
		assert exit_code != 0
		assert "No clients found" in stderr
		assert "supplied clientId filter:" in stderr
		assert "pytest-client1.test.tld." in stderr

	service_client.productOnDepot_getIdents.assert_not_called()


@pytest.mark.opsi_service
def test_list_product_client_state(admin_service_client: ServiceClient) -> None:
	with (
		tmp_client(admin_service_client, CLIENT_ID_1),
		tmp_client(admin_service_client, CLIENT_ID_2),
		tmp_product(admin_service_client, PRODUCT_ID_1) as product_1,
		tmp_product(admin_service_client, PRODUCT_ID_2) as product_2,
	):
		admin_service_client.jsonrpc(
			"productOnClient_createObjects",
			params=[
				[
					{
						"clientId": CLIENT_ID_1,
						"productId": PRODUCT_ID_1,
						"productType": product_1.getType(),
						"productVersion": product_1.productVersion,
						"packageVersion": product_1.packageVersion,
						"installationStatus": "installed",
						"actionRequest": "none",
					},
					{
						"clientId": CLIENT_ID_2,
						"productId": PRODUCT_ID_2,
						"productType": product_2.getType(),
						"installationStatus": "unknown",
						"actionRequest": "setup",
					},
				]
			],
		)

		# all clients, all products, all statuses / action-requests
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"product-client-state",
				"list",
				"--where",
				"clientId=*",
				"--where",
				"productId=pytest*",
			]
		)
		assert exit_code == 0

		rows = stdout_into_list(_stdout)[1:]
		assert len(rows) == 4

		state_map = {(row[0], row[1]): row for row in rows}
		assert state_map[(CLIENT_ID_1, PRODUCT_ID_1)][5:7] == ["installed", "none"]
		assert state_map[(CLIENT_ID_2, PRODUCT_ID_2)][5:7] == ["unknown", "setup"]
		assert state_map[(CLIENT_ID_1, PRODUCT_ID_2)][5:7] == ["not_installed", "none"]
		assert state_map[(CLIENT_ID_2, PRODUCT_ID_1)][5:7] == ["not_installed", "none"]

		# filter by installed + none -> only client1 / product1
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"product-client-state",
				"list",
				"--where",
				"clientId=*",
				"--where",
				"productId=pytest*",
				"--where",
				"installationStatus=installed",
				"--where",
				"actionRequest=none",
			]
		)
		assert exit_code == 0
		filtered_rows = stdout_into_list(_stdout)
		assert len(filtered_rows) - 1 == 1
		assert filtered_rows[1][0] == CLIENT_ID_1
		assert filtered_rows[1][1] == PRODUCT_ID_1
		assert filtered_rows[1][5] == "installed"
		assert filtered_rows[1][6] == "none"

		# filter by unknown + setup -> only client2 / product2
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"product-client-state",
				"list",
				"--where",
				"clientId=*",
				"--where",
				"productId=pytest*",
				"--where",
				"installationStatus=unknown",
				"--where",
				"actionRequest=setup",
			]
		)
		assert exit_code == 0
		filtered_rows = stdout_into_list(_stdout)
		assert len(filtered_rows) - 1 == 1
		assert filtered_rows[1][0] == CLIENT_ID_2
		assert filtered_rows[1][1] == PRODUCT_ID_2
		assert filtered_rows[1][5] == "unknown"
		assert filtered_rows[1][6] == "setup"


@pytest.mark.opsi_service
def test_apply_product_client_state(admin_service_client: ServiceClient) -> None:
	with (
		tmp_client(admin_service_client, CLIENT_ID_1),
		tmp_client(admin_service_client, CLIENT_ID_2),
		tmp_product(admin_service_client, PRODUCT_ID_1) as product_1,
		tmp_product(admin_service_client, PRODUCT_ID_2) as product_2,
	):
		update_data = [
			{
				"clientId": CLIENT_ID_1,
				"productId": PRODUCT_ID_1,
				"productType": product_1.getType(),
				"productVersion": product_1.productVersion,
				"packageVersion": product_1.packageVersion,
				"installationStatus": "installed",
				"actionRequest": "setup",
			},
			{
				"clientId": CLIENT_ID_2,
				"productId": PRODUCT_ID_2,
				"productType": product_2.getType(),
				"productVersion": product_2.productVersion,
				"packageVersion": product_2.packageVersion,
				"installationStatus": "unknown",
				"actionRequest": "none",
			},
		]

		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"product-client-state",
				"apply",
			],
			stdin=[json.dumps(update_data)],
		)
		assert exit_code == 0

		pocs = admin_service_client.productOnClient_getObjects(  # ty: ignore[unresolved-attribute]
			clientId=[CLIENT_ID_1, CLIENT_ID_2],
			productId=[PRODUCT_ID_1, PRODUCT_ID_2],
		)
		assert len(pocs) == 2

		state_map = {(poc.clientId, poc.productId): poc for poc in pocs}

		assert state_map[(CLIENT_ID_1, PRODUCT_ID_1)].installationStatus == "installed"
		assert state_map[(CLIENT_ID_1, PRODUCT_ID_1)].actionRequest == "setup"
		assert state_map[(CLIENT_ID_1, PRODUCT_ID_1)].productVersion == product_1.productVersion
		assert state_map[(CLIENT_ID_1, PRODUCT_ID_1)].packageVersion == product_1.packageVersion

		assert state_map[(CLIENT_ID_2, PRODUCT_ID_2)].installationStatus == "unknown"
		assert state_map[(CLIENT_ID_2, PRODUCT_ID_2)].actionRequest == "none"
		assert state_map[(CLIENT_ID_2, PRODUCT_ID_2)].productVersion == product_2.productVersion
		assert state_map[(CLIENT_ID_2, PRODUCT_ID_2)].packageVersion == product_2.packageVersion
