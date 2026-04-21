# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import json
import time
from contextlib import ExitStack
from pathlib import Path

import pytest
from opsicommon.client.opsiservice import ServiceClient

from tests.utils import run_cli, stdout_into_list, tmp_client, tmp_product

CLIENT_ID_1 = "pytest-client1.test.tld"
CLIENT_ID_2 = "pytest-client2.test.tld"

PRODUCT_ID_1 = "pytest-product1"
PRODUCT_ID_2 = "pytest-product2"


# ===============
# HELP FUNCTIONS
# ===============


# get products from depot and setting locked to 'True' manually
# update depot with locked products
def lock_products(admin_service_client: ServiceClient, product_id: str | None = None) -> None:
	products = admin_service_client.productOnDepot_getObjects(productId=product_id or [])  # type:ignore[attr-defined]
	for product in products:
		product.locked = True
	admin_service_client.productOnDepot_updateObjects(products)  # type:ignore[attr-defined]


# unlock products with given product-id and depot-id
def unlock_products(product_ids: list[str] = [], depot_ids: list[str] = []) -> tuple[int, str, str]:
	args = ["datastore", "product", "unlock"]
	if product_ids:
		args += ["--product-ids", ",".join(product_ids)]
	if depot_ids:
		args += ["--depot-ids", ",".join(depot_ids)]
	return run_cli(args)


# verify the given locked status (e.g. is product.locked = True or False?)
def verify_lock_status(admin_service_client: ServiceClient, is_locked: bool, product_id: str | None = None) -> None:
	products = admin_service_client.productOnDepot_getObjects(productId=product_id or [])  # type:ignore[attr-defined]
	for prod in products:
		assert prod.locked is is_locked


# install broken package -> failed installation
def install_broken_package() -> None:
	package_name = "gimp2_broken_1.0-1.opsi"
	broken_package = Path(f"tests/test_data/plugins/package/{package_name}")
	run_cli(["package", "install", str(broken_package)])


def uninstall_broken_package() -> None:
	run_cli(["package", "uninstall", "gimp2_broken_1.0-1.opsi"])


# =========
# PYTESTS
# =========


# ===================================(PRODUCT UNLOCK || TESTS)============================================
# lock one product -> verify -> unlock (CLI) -> verify
@pytest.mark.opsi_service
def test_product_unlock_manual(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		lock_products(admin_service_client)
		verify_lock_status(admin_service_client, is_locked=True)
		unlock_products()
		verify_lock_status(admin_service_client, is_locked=False)


# lock list of products -> verify -> unlock (CLI) -> verify
@pytest.mark.opsi_service
def test_product_unlock_multiple(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		lock_products(admin_service_client)
		verify_lock_status(admin_service_client, is_locked=True)
		unlock_products(product_ids=["gimp2", "test2", "pytest-product1", "pytest-product2", "opsi-client-agent"])
		verify_lock_status(admin_service_client, is_locked=False)


# lock product (failed installation) -> verify -> unlock (CLI) -> verify
@pytest.mark.opsi_service
def test_product_unlock_installation(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		install_broken_package()
		verify_lock_status(admin_service_client, is_locked=True, product_id="gimp2")
		unlock_products(product_ids=["gimp2"])
		verify_lock_status(admin_service_client, is_locked=False, product_id="gimp2")


# lock products -> verify -> try unlock (wrong/mutliple depot-ids) -> verify error message
@pytest.mark.opsi_service
def test_wrong_depot_id(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		lock_products(admin_service_client)
		verify_lock_status(admin_service_client, is_locked=True)
		exitcode, _stdout, stderr = unlock_products(depot_ids=["hallo,test"])
		assert exitcode != 0
		assert "No such depot(s)" in stderr


@pytest.mark.opsi_service
def _test_product_property_list_stress_test(admin_service_client: ServiceClient) -> None:
	num_clients = 1
	num_products = 5
	num_properties = 3
	tmp_clients = []
	tmp_products = []

	# create clients
	i = 0
	while i < num_clients:
		tmp_clients.append(tmp_client(admin_service_client, f"pytest-client{i}.test.tld"))
		i += 1
	# create products
	j = 0
	while j < num_products:
		tmp_products.append(tmp_product(admin_service_client, f"pytest-product{j}"))
		j += 1

	with ExitStack() as stack:
		for client in tmp_clients:
			stack.enter_context(client)
		for product in tmp_products:
			stack.enter_context(product)

		# create properties and their property-states
		i = 0
		while i < num_clients:
			j = 0
			while j < num_products:
				k = 0
				while k < num_properties:
					admin_service_client.productProperty_create(  # type: ignore[unresolved-attribute]
						productId=f"pytest-product{j}",
						productVersion="1",
						packageVersion="1",
						propertyId=f"property{k}",
					)
					admin_service_client.productPropertyState_create(  # type: ignore[unresolved-attribute]
						productId=f"pytest-product{j}",
						propertyId=f"property{k}",
						objectId=f"pytest-client{i}.test.tld",
					)
					print(f"pytest-client{i}.test.tld; pytest-product{j}; property{k}")
					k += 1
				j += 1
			i += 1

		start = time.perf_counter()
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"product-property-state",
				"list",
				"--object-ids",
				"all",
				"--product-ids",
				"pytest*",
				"--property-ids",
				"property*",
			]
		)
		assert exit_code == 0
		assert len(stdout_into_list(_stdout)) - 1 == num_clients * num_products * num_properties
	diff = time.perf_counter() - start

	print(diff)


# ===================================(PRODUCT-CLIENT-STATE LIST || TESTS)============================================
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
def test_update_product_client_state(admin_service_client: ServiceClient) -> None:
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
				"update",
			],
			stdin=[json.dumps(update_data)],
		)
		assert exit_code == 0

		pocs = admin_service_client.productOnClient_getObjects(  # type: ignore[attr-defined]
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
