import json
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest
from opsicommon.client.opsiservice import ServiceClient

from .utils import run_cli, tmp_client, tmp_product

CLIENT_ID_1 = "pytest-client1.test.tld"
CLIENT_ID_2 = "pytest-client2.test.tld"
CLIENT_ID_3 = "client3.test.tld"
CLIENT_ID_4 = "client4.test.tld"
CLIENT_ID_WILDCARD_1 = "py*"
CLIENT_ID_WILDCARD_2 = "cli*"
CLIENT_ID_WILDCARD_3 = "pyt*"
CLIENT_ID_WILDCARD_4 = "clie*"

PRODUCT_ID_1 = "pytest-product1"
PRODUCT_ID_2 = "pytest-product2"
PROPERTY_ID_1 = "property1"
PROPERTY_ID_2 = "property2"

CONFIG_ID_1 = "opsi.check.enabled"
CONFIG_ID_2 = "opsi.check.ignore_products"
BOOL_CONFIG = "opsi.check.enabled"
UNICODE_CONFIG_ONE = "clientconfig.depot.drive"
UNICODE_CONFIG_MULTI = "opsi.check.ignore_products"


# ===============
# HELP FUNCTIONS
# ===============
def stdout_into_list(_stdout: str) -> list[list[str]]:
	stdout_result_list = []
	stdout_list = _stdout.splitlines()
	list_len = len(stdout_list)
	i = 0

	# not pretty but working
	while i < list_len:
		line = stdout_list[i]
		line_as_list = line.split(";")
		if "netboot.grub.additional_menu_entries" in line_as_list:
			line_as_list = [
				line_as_list[0],
				"netboot.grub.additional_menu_entries",
				"if [ $grub_platform = efi ]; then menuentry 'UEFI Firmware Settings' --class firmware {fwsetup}fi",
				stdout_list[i + 5].split(";")[1],
			]
			i += 5
		stdout_result_list.append(line_as_list)
		i += 1
	return stdout_result_list


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


# ===================================(CONFIG-STATE LIST || TESTS)============================================
@pytest.mark.opsi_service
def test_config_state_list(admin_service_client: ServiceClient) -> None:
	with (
		tmp_client(admin_service_client, CLIENT_ID_1),
		tmp_client(admin_service_client, CLIENT_ID_2),
		tmp_client(admin_service_client, CLIENT_ID_3),
		tmp_client(admin_service_client, CLIENT_ID_4),
	):
		all_configs = admin_service_client.jsonrpc("config_getObjects", params=[])
		client_to_depot_objects = admin_service_client.configState_getClientToDepotserver()  # type:ignore[attr-defined]
		DEPOT_ID = client_to_depot_objects[0]["depotId"]

		# One objectId, one configId
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				f"{CLIENT_ID_1}",
				"--config-ids",
				f"{CONFIG_ID_1}",
			]
		)
		assert exit_code == 0
		print(_stdout)
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[1][1] == CONFIG_ID_1
		assert len(stdout_into_list(_stdout)) - 1 == 1

		# One objectId, all configId's
		exit_code, _stdout, _stderr = run_cli(
			["--output-format", "csv", "datastore", "config-state", "list", "--object-ids", f"{CLIENT_ID_1}", "--config-ids", "all"]
		)
		assert exit_code == 0
		stdout_list = stdout_into_list(_stdout)
		for element in stdout_list[1:]:
			assert element[0] == CLIENT_ID_1
		# test if all configs are shown in output table
		assert len(stdout_list) - 1 == len(all_configs)

		# All objectId's (4), one configId
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				"all",
				"--config-ids",
				f"{CONFIG_ID_1}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_3
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_4
		assert stdout_into_list(_stdout)[3][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[4][0] == CLIENT_ID_2
		assert len(stdout_into_list(_stdout)) - 1 == 4

		# All objectId's (2), all configId's
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				"all",
				"--config-ids",
				"all",
			]
		)
		assert exit_code == 0
		assert len(stdout_into_list(_stdout)) - 1 == 4 * len(all_configs)

		# comma-separated config-ids
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				"all",
				"--config-ids",
				f"{CONFIG_ID_1},{CONFIG_ID_2}",
			]
		)
		assert exit_code == 0
		assert len(stdout_into_list(_stdout)) - 1 == 8

		# (Depot)
		# test if the origin and changed value of a config is shown correctly
		# opsi.check.enabled: False("0") -> True("1")
		# configs for DEPOT
		CONFIGSTATE_1_DEPOT = {"configId": f"{CONFIG_ID_1}", "objectId": f"{DEPOT_ID}", "values": False}
		CONFIGSTATE_2_DEPOT = {"configId": f"{CONFIG_ID_1}", "objectId": f"{DEPOT_ID}", "values": True}

		admin_service_client.jsonrpc("configState_createObjects", params=[CONFIGSTATE_1_DEPOT])
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				f"{CLIENT_ID_1}",
				"--config-ids",
				f"{CONFIG_ID_1}",
			]
		)
		assert exit_code == 0
		print(_stdout)
		print(stdout_into_list(_stdout))
		assert (
			stdout_into_list(_stdout)[1][2] == "0"
		)  # only second row is of interest, first row of stdout_list[0][i]=([clientId, configId, value, origin])
		assert stdout_into_list(_stdout)[1][3] == "depot"

		admin_service_client.jsonrpc("configState_updateObjects", params=[CONFIGSTATE_2_DEPOT])
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				f"{CLIENT_ID_1}",
				"--config-ids",
				f"{CONFIG_ID_1}",
			]
		)
		assert exit_code == 0
		assert (
			stdout_into_list(_stdout)[1][2] == "1"
		)  # only second row is of interest, first row of stdout_list[0][i]=([clientId, configId, value, origin])
		assert stdout_into_list(_stdout)[1][3] == "depot"

		# (CLIENT)
		# test if the origin and changed value of a config is shown correctly
		# opsi.check.enabled: True("1") -> False("0")
		# check if CLIENT overrides origin from depot -> client
		# configs for CLIENT_1
		CONFIGSTATE_1_CLIENT_1 = {"configId": f"{CONFIG_ID_1}", "objectId": f"{CLIENT_ID_1}", "values": True}
		CONFIGSTATE_2_CLIENT_1 = {"configId": f"{CONFIG_ID_1}", "objectId": f"{CLIENT_ID_1}", "values": False}

		admin_service_client.jsonrpc("configState_createObjects", params=[CONFIGSTATE_1_CLIENT_1])
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				f"{CLIENT_ID_1}",
				"--config-ids",
				f"{CONFIG_ID_1}",
			]
		)
		assert exit_code == 0
		assert (
			stdout_into_list(_stdout)[1][2] == "1"
		)  # only second row is of interest, first row of stdout_list[0][i]=([clientId, configId, value, origin])
		assert stdout_into_list(_stdout)[1][3] == "client"

		admin_service_client.jsonrpc("configState_updateObjects", params=[CONFIGSTATE_2_CLIENT_1])
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				f"{CLIENT_ID_1}",
				"--config-ids",
				f"{CONFIG_ID_1}",
			]
		)
		assert exit_code == 0
		assert (
			stdout_into_list(_stdout)[1][2] == "0"
		)  # only second row is of interest, first row of stdout_list[0][i]=([clientId, configId, value, origin])
		assert stdout_into_list(_stdout)[1][3] == "client"

		# test comma seperated objectId's and comma seperated objectId's with wildcards
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				f"{CLIENT_ID_3},{CLIENT_ID_4}",
				"--config-ids",
				f"{CONFIG_ID_1}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_3
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_4
		assert len(stdout_into_list(_stdout)) - 1 == 2

		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				f"{CLIENT_ID_WILDCARD_1},{CLIENT_ID_WILDCARD_2}",
				"--config-ids",
				f"{CONFIG_ID_1}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_3
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_4
		assert stdout_into_list(_stdout)[3][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[4][0] == CLIENT_ID_2
		assert len(stdout_into_list(_stdout)) - 1 == 4

		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				f"{CLIENT_ID_WILDCARD_1},{CLIENT_ID_WILDCARD_3}",
				"--config-ids",
				f"{CONFIG_ID_1}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_2
		assert len(stdout_into_list(_stdout)) - 1 == 2

		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"list",
				"--object-ids",
				f"{CLIENT_ID_WILDCARD_1},{CLIENT_ID_WILDCARD_2},{CLIENT_ID_WILDCARD_3},{CLIENT_ID_WILDCARD_4}",
				"--config-ids",
				f"{CONFIG_ID_1}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_3
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_4
		assert stdout_into_list(_stdout)[3][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[4][0] == CLIENT_ID_2
		assert len(stdout_into_list(_stdout)) - 1 == 4


# ===================================(CONFIG-STATE SET || TESTS)============================================
@pytest.mark.parametrize(
	"config, object_id, value_in, value_out",
	[
		(BOOL_CONFIG, CLIENT_ID_1, ["true"], [True]),  # set Bool -> create configState
		(BOOL_CONFIG, CLIENT_ID_2, ["True"], [True]),
		(BOOL_CONFIG, CLIENT_ID_1, ["false"], [False]),  # set Bool -> update configState
		(BOOL_CONFIG, CLIENT_ID_2, ["False"], [False]),
		(BOOL_CONFIG, "all", ["true"], [True]),  # set Bool -> objectId='all'
		(BOOL_CONFIG, "all", ["True"], [True]),
		(UNICODE_CONFIG_ONE, CLIENT_ID_1, ["c:"], ["c:"]),  # set Unicode -> create configState
		(UNICODE_CONFIG_ONE, CLIENT_ID_2, ["d:"], ["d:"]),
		(UNICODE_CONFIG_ONE, CLIENT_ID_1, ["d:"], ["d:"]),  # set Unicode -> update configState
		(UNICODE_CONFIG_ONE, CLIENT_ID_2, ["c:"], ["c:"]),
		(UNICODE_CONFIG_ONE, "all", ["f:"], ["f:"]),  # set Unicode -> objectId='all'
		(UNICODE_CONFIG_ONE, "all", ["g:"], ["g:"]),
		(UNICODE_CONFIG_MULTI, CLIENT_ID_1, ["a, b, c"], ["a", "b", "c"]),  # set Unicode MultiValue-> create configState
		(UNICODE_CONFIG_MULTI, CLIENT_ID_2, ["a, b, d"], ["a", "b", "d"]),
		(UNICODE_CONFIG_MULTI, CLIENT_ID_1, ["d, e, f"], ["d", "e", "f"]),  # set Unicode MultiValue-> update configState
		(UNICODE_CONFIG_MULTI, CLIENT_ID_2, ["d, e, f"], ["d", "e", "f"]),
		(UNICODE_CONFIG_MULTI, "all", ["1, 2, 3"], ["1", "2", "3"]),  # set Unicode MultiValue-> objectId='all'
		(UNICODE_CONFIG_MULTI, "all", ["3, 4, 5"], ["3", "4", "5"]),
	],
)
@pytest.mark.opsi_service
def test_config_state_set(
	admin_service_client: ServiceClient, config: str, object_id: str, value_in: list[str], value_out: list[str | bool]
) -> None:
	with (
		tmp_client(admin_service_client, CLIENT_ID_1),
		tmp_client(admin_service_client, CLIENT_ID_2),
	):
		if object_id == "all":
			host_objects = admin_service_client.host_getObjects(id=[], type="OpsiClient")  # type: ignore[attr-defined]
			object_ids = [obj.id for obj in host_objects]
			for object_id in object_ids:
				exit_code, _stdout, _stderr = run_cli(
					["datastore", "config-state", "set"] + [object_id] + [config] + ["--values"] + value_in
				)
				assert exit_code == 0
				assert admin_service_client.configState_getValues(config, [object_id])[object_id][config] == value_out  # type: ignore[attr-defined]
		else:
			exit_code, _stdout, _stderr = run_cli(
				[
					"datastore",
					"config-state",
					"set",
				]
				+ [object_id]
				+ [config]
				+ ["--values"]
				+ value_in
			)
			assert exit_code == 0
			assert admin_service_client.configState_getValues(config, [object_id])[object_id][config] == value_out  # type: ignore[attr-defined]


# trigger errors and checking wrong input
@pytest.mark.opsi_service
def test_config_state_set_errors(admin_service_client: ServiceClient) -> None:
	with (
		tmp_client(admin_service_client, CLIENT_ID_1),
		tmp_client(admin_service_client, CLIENT_ID_2),
	):
		# - bool config and wrong value
		exit_code, _stdout, _stderr = run_cli(
			["datastore", "config-state", "set"] + [CLIENT_ID_1] + [BOOL_CONFIG] + ["--values"] + ["test"]
		)
		assert exit_code != 0
		assert f"'test' is not valid for {BOOL_CONFIG}." in _stderr
		assert "Possible values are: [" in _stderr  # depending on monitor resolution output may contain line breaks

		# - bool config and multiple value
		exit_code, _stdout, _stderr = run_cli(
			["datastore", "config-state", "set"] + [CLIENT_ID_1] + [BOOL_CONFIG] + ["--values"] + ["test, testing"]
		)
		assert exit_code != 0
		assert f"Multivalues are not valid for {BOOL_CONFIG}" in _stderr
		assert "Possible values are: [" in _stderr  # depending on monitor resolution output may contain line breaks

		# - unicode config and multiple values
		exit_code, _stdout, _stderr = run_cli(
			["datastore", "config-state", "set"] + [CLIENT_ID_1] + [UNICODE_CONFIG_ONE] + ["--values"] + ["g:, h:"]
		)
		assert exit_code != 0
		assert f"Value is not valid for {UNICODE_CONFIG_ONE}." in _stderr
		assert "Multivalues are not allowed." in _stderr

		# - unicode config and wrong value
		exit_code, _stdout, _stderr = run_cli(
			["datastore", "config-state", "set"] + [CLIENT_ID_1] + [UNICODE_CONFIG_ONE] + ["--values"] + ["test"]
		)
		assert exit_code != 0
		assert f"Value is not valid for {UNICODE_CONFIG_ONE}." in _stderr
		assert "Possible values are:" in _stderr


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


# ===================================(PRODUCT-PROPTERY-STATE LIST || TESTS)============================================
@pytest.mark.opsi_service
def test_product_property_list(admin_service_client: ServiceClient) -> None:
	start = time.perf_counter()
	with (
		tmp_client(admin_service_client, CLIENT_ID_1),
		tmp_client(admin_service_client, CLIENT_ID_2),
		tmp_product(admin_service_client, PRODUCT_ID_1),
		tmp_product(admin_service_client, PRODUCT_ID_2),
	):
		client_to_depot_objects = admin_service_client.configState_getClientToDepotserver()  # type:ignore[attr-defined]
		DEPOT_ID = client_to_depot_objects[0]["depotId"]

		# add PRODUCT-PROPERTIES
		admin_service_client.productProperty_create(  # type:ignore[attr-defined]
			productId=PRODUCT_ID_1,
			productVersion="1",
			packageVersion="1",
			propertyId=PROPERTY_ID_1,
		)
		admin_service_client.productProperty_create(  # type:ignore[attr-defined]
			productId=PRODUCT_ID_2, productVersion="1", packageVersion="1", propertyId=PROPERTY_ID_2
		)
		admin_service_client.productProperty_create(  # type:ignore[attr-defined]
			productId=PRODUCT_ID_1,
			productVersion="1",
			packageVersion="1",
			propertyId=PROPERTY_ID_2,
		)
		admin_service_client.productProperty_create(  # type:ignore[attr-defined]
			productId=PRODUCT_ID_2, productVersion="1", packageVersion="1", propertyId=PROPERTY_ID_1
		)

		# add PRODUCT-PROPERTY-STATES for client 1 & 2
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_1, propertyId=PROPERTY_ID_1, objectId=CLIENT_ID_1)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_1, propertyId=PROPERTY_ID_1, objectId=CLIENT_ID_2)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_1, propertyId=PROPERTY_ID_2, objectId=CLIENT_ID_1)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_1, propertyId=PROPERTY_ID_2, objectId=CLIENT_ID_2)  # type:ignore[attr-defined]

		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_2, propertyId=PROPERTY_ID_1, objectId=CLIENT_ID_1)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_2, propertyId=PROPERTY_ID_1, objectId=CLIENT_ID_2)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_2, propertyId=PROPERTY_ID_2, objectId=CLIENT_ID_1)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_2, propertyId=PROPERTY_ID_2, objectId=CLIENT_ID_2)  # type:ignore[attr-defined]

		# One productId, one propertyId, no object-id
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
				f"{PRODUCT_ID_1}",
				"--property-ids",
				f"{PROPERTY_ID_1}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[1][1] == PRODUCT_ID_1
		assert stdout_into_list(_stdout)[1][2] == PROPERTY_ID_1
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_2
		assert stdout_into_list(_stdout)[2][1] == PRODUCT_ID_1
		assert stdout_into_list(_stdout)[2][2] == PROPERTY_ID_1
		assert len(stdout_into_list(_stdout)) - 1 == 2

		# One productId, one propertyId, object-id=py*
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
				"py*",
				"--product-ids",
				f"{PRODUCT_ID_2}",
				"--property-ids",
				f"{PROPERTY_ID_2}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[1][1] == PRODUCT_ID_2
		assert stdout_into_list(_stdout)[1][2] == PROPERTY_ID_2
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_2
		assert stdout_into_list(_stdout)[2][1] == PRODUCT_ID_2
		assert stdout_into_list(_stdout)[2][2] == PROPERTY_ID_2
		assert len(stdout_into_list(_stdout)) - 1 == 2

		# One productId, one propertyId, object-id=comma separated
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
				f"{CLIENT_ID_1},{CLIENT_ID_2}",
				"--product-ids",
				f"{PRODUCT_ID_2}",
				"--property-ids",
				f"{PROPERTY_ID_2}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[1][1] == PRODUCT_ID_2
		assert stdout_into_list(_stdout)[1][2] == PROPERTY_ID_2
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_2
		assert stdout_into_list(_stdout)[2][1] == PRODUCT_ID_2
		assert stdout_into_list(_stdout)[2][2] == PROPERTY_ID_2
		assert len(stdout_into_list(_stdout)) - 1 == 2

		# product-id=pytest*, property-id=proper*, object-id=py*
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
				"py*",
				"--product-ids",
				"pytest*",
				"--property-ids",
				"proper*",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][:3] == [CLIENT_ID_1, PRODUCT_ID_1, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[2][:3] == [CLIENT_ID_1, PRODUCT_ID_1, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[3][:3] == [CLIENT_ID_1, PRODUCT_ID_2, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[4][:3] == [CLIENT_ID_1, PRODUCT_ID_2, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[5][:3] == [CLIENT_ID_2, PRODUCT_ID_1, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[6][:3] == [CLIENT_ID_2, PRODUCT_ID_1, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[7][:3] == [CLIENT_ID_2, PRODUCT_ID_2, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[8][:3] == [CLIENT_ID_2, PRODUCT_ID_2, PROPERTY_ID_2]
		assert len(stdout_into_list(_stdout)) - 1 == 8

		# product-id=comma-separated, property-id=comma-separated, object-id=comma-separated
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
				f"{CLIENT_ID_1},{CLIENT_ID_2}",
				"--product-ids",
				f"{PRODUCT_ID_1},{PRODUCT_ID_2}",
				"--property-ids",
				f"{PROPERTY_ID_1},{PROPERTY_ID_2}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][:3] == [CLIENT_ID_1, PRODUCT_ID_1, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[2][:3] == [CLIENT_ID_1, PRODUCT_ID_1, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[3][:3] == [CLIENT_ID_1, PRODUCT_ID_2, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[4][:3] == [CLIENT_ID_1, PRODUCT_ID_2, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[5][:3] == [CLIENT_ID_2, PRODUCT_ID_1, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[6][:3] == [CLIENT_ID_2, PRODUCT_ID_1, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[7][:3] == [CLIENT_ID_2, PRODUCT_ID_2, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[8][:3] == [CLIENT_ID_2, PRODUCT_ID_2, PROPERTY_ID_2]
		assert len(stdout_into_list(_stdout)) - 1 == 8

		# object-id is a depot-id
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
				f"{DEPOT_ID}",
				"--product-ids",
				"pytest*",
				"--property-ids",
				"all",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][:3] == [DEPOT_ID, PRODUCT_ID_1, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[2][:3] == [DEPOT_ID, PRODUCT_ID_1, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[3][:3] == [DEPOT_ID, PRODUCT_ID_2, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[4][:3] == [DEPOT_ID, PRODUCT_ID_2, PROPERTY_ID_2]
		assert len(stdout_into_list(_stdout)) - 1 == 4

	diff = time.perf_counter() - start
	print(diff)


@pytest.mark.opsi_service
def test_product_property_list_stress_test(admin_service_client: ServiceClient) -> None:
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
					admin_service_client.productProperty_create(
						productId=f"pytest-product{j}",
						productVersion="1",
						packageVersion="1",
						propertyId=f"property{k}",
					)
					admin_service_client.productPropertyState_create(
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
				"--client-ids",
				"all",
				"--product-ids",
				"pytest*",
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
				"--client-ids",
				"all",
				"--product-ids",
				"pytest*",
				"--installation-statuses",
				"installed",
				"--action-requests",
				"none",
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
				"--client-ids",
				"all",
				"--product-ids",
				"pytest*",
				"--installation-statuses",
				"unknown",
				"--action-requests",
				"setup",
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


@pytest.mark.opsi_service
def test_list_clients(admin_service_client: ServiceClient) -> None:
	with (
		tmp_client(admin_service_client, CLIENT_ID_1),
		tmp_client(admin_service_client, CLIENT_ID_2),
		tmp_client(admin_service_client, CLIENT_ID_3),
		tmp_client(admin_service_client, CLIENT_ID_4),
	):
		# all clients
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"id",
				"datastore",
				"client",
				"list",
				"--client-ids",
				"all",
			]
		)
		assert exit_code == 0
		rows = stdout_into_list(_stdout)[1:]
		returned_ids = [row[0] for row in rows]
		assert CLIENT_ID_1 in returned_ids
		assert CLIENT_ID_2 in returned_ids
		assert CLIENT_ID_3 in returned_ids
		assert CLIENT_ID_4 in returned_ids

		# wildcard filter
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"id",
				"datastore",
				"client",
				"list",
				"--client-ids",
				"py*",
			]
		)
		assert exit_code == 0
		rows = stdout_into_list(_stdout)[1:]
		assert len(rows) == 2
		assert rows[0][0] == CLIENT_ID_1
		assert rows[1][0] == CLIENT_ID_2

		# comma separated ids
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"id",
				"datastore",
				"client",
				"list",
				"--client-ids",
				f"{CLIENT_ID_3},{CLIENT_ID_4}",
			]
		)
		assert exit_code == 0
		rows = stdout_into_list(_stdout)[1:]
		assert len(rows) == 2
		assert rows[0][0] == CLIENT_ID_3
		assert rows[1][0] == CLIENT_ID_4


@pytest.mark.opsi_service
@pytest.mark.parametrize("dry_run", (True, False))
def test_update_clients(admin_service_client: ServiceClient, dry_run: bool) -> None:
	with (
		tmp_client(admin_service_client, CLIENT_ID_1),
		tmp_client(admin_service_client, CLIENT_ID_2),
	):
		update_data = [
			{
				"id": CLIENT_ID_1,
				"description": "pytest description 1",
				"inventoryNumber": "inv-001",
			},
			{
				"id": CLIENT_ID_2,
				"description": "pytest description 2",
				"inventoryNumber": "inv-002",
			},
		]

		exit_code, _stdout, _stderr = run_cli(
			(["--dry-run"] if dry_run else [])
			+ [
				"--output-format",
				"csv",
				"datastore",
				"client",
				"update",
			],
			stdin=[json.dumps(update_data)],
		)
		assert exit_code == 0

		hosts = admin_service_client.host_getObjects(id=[CLIENT_ID_1, CLIENT_ID_2], type="OpsiClient")  # type: ignore[attr-defined]
		assert len(hosts) == 2
		host_map = {host.id: host for host in hosts}

		if dry_run:
			assert host_map[CLIENT_ID_1].description == ""
			assert host_map[CLIENT_ID_2].description == ""
			assert host_map[CLIENT_ID_1].inventoryNumber == ""
			assert host_map[CLIENT_ID_2].inventoryNumber == ""
		else:
			assert host_map[CLIENT_ID_1].description == "pytest description 1"
			assert host_map[CLIENT_ID_2].description == "pytest description 2"
			assert host_map[CLIENT_ID_1].inventoryNumber == "inv-001"
			assert host_map[CLIENT_ID_2].inventoryNumber == "inv-002"


@pytest.mark.opsi_service
def test_edit_clients_non_interactive(admin_service_client: ServiceClient) -> None:
	with tmp_client(admin_service_client, CLIENT_ID_1):
		exit_code, _stdout, _stderr = run_cli(
			[
				"datastore",
				"client",
				"edit",
				"--client-ids",
				CLIENT_ID_1,
			]
		)
		assert exit_code != 0
		assert "Editing is not possible in non-interactive mode." in _stderr


@pytest.mark.opsi_service
def test_edit_clients(admin_service_client: ServiceClient) -> None:
	with tmp_client(admin_service_client, CLIENT_ID_1):
		admin_service_client.jsonrpc(
			"host_updateObjects",
			[[{"id": CLIENT_ID_1, "type": "OpsiClient", "description": "before edit", "inventoryNumber": "before-001"}]],
		)

		def fake_editor(cmd: list[str]) -> None:
			edit_file = Path(cmd[-1])
			clients = json.loads(edit_file.read_text(encoding="utf-8"))
			clients[0]["description"] = "after edit"
			clients[0]["inventoryNumber"] = "after-001"
			edit_file.write_text(json.dumps(clients, indent=2), encoding="utf-8")

		with patch("subprocess.run", side_effect=fake_editor):
			exit_code, _stdout, _stderr = run_cli(
				[
					"--interactive",
					"datastore",
					"client",
					"edit",
					"--client-ids",
					CLIENT_ID_1,
				]
			)

		assert exit_code == 0
		host = admin_service_client.host_getObjects(id=[CLIENT_ID_1], type="OpsiClient")[0]  # type: ignore[attr-defined]
		assert host.description == "after edit"
		assert host.inventoryNumber == "after-001"
