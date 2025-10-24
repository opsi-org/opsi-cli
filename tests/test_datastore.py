from pathlib import Path

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

CONFIG_ID = "opsi.check.enabled"
BOOL_CONFIG = "opsi.check.enabled"
UNICODE_CONFIG_ONE = "clientconfig.depot.drive"
UNICODE_CONFIG_MULTI = "opsi.check.ignore_products"


def stdout_into_list(_stdout: str) -> list[list[str]]:
	stdout_result_list = []
	stdout_list = _stdout.splitlines()
	list_len = len(stdout_list)
	i = 0

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
def unlock_products(product_id: list[str] = [], depot_id: list[str] = []) -> tuple[int, str, str]:
	if depot_id:
		return run_cli(["datastore", "product", "unlock"] + product_id + ["--depot-id"] + depot_id)
	else:
		return run_cli(["datastore", "product", "unlock"] + product_id)


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


# ===================================CONFIG-STATE LIST TESTS============================================
@pytest.mark.opsi_service
def test_config_state_list(admin_service_client: ServiceClient) -> None:
	with (
		tmp_client(admin_service_client, CLIENT_ID_1),
		tmp_client(admin_service_client, CLIENT_ID_2),
		tmp_client(admin_service_client, CLIENT_ID_3),
		tmp_client(admin_service_client, CLIENT_ID_4),
	):
		all_configs = admin_service_client.jsonrpc("config_getObjects", params=[])  # type:ignore[attr-defined]
		client_to_server_objects = admin_service_client.configState_getClientToDepotserver()  # type:ignore[attr-defined]
		DEPOT_ID = client_to_server_objects[0]["depotId"]

		# One objectId, one configId
		exit_code, _stdout, _stderr = run_cli(
			["--output-format", "csv", "datastore", "config-state", "list", "--object-id", f"{CLIENT_ID_1}", "--config-id", f"{CONFIG_ID}"]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[1][1] == CONFIG_ID
		assert len(stdout_into_list(_stdout)) - 1 == 1

		# One objectId, all configId's
		exit_code, _stdout, _stderr = run_cli(
			["--output-format", "csv", "datastore", "config-state", "list", "--object-id", f"{CLIENT_ID_1}"]
		)
		assert exit_code == 0
		stdout_list = stdout_into_list(_stdout)
		for element in stdout_list[1:]:
			assert element[0] == CLIENT_ID_1
		# test if all configs are shown in output table
		assert len(stdout_list) - 1 == len(all_configs)

		# All objectId's (4), one configId
		exit_code, _stdout, _stderr = run_cli(
			["--output-format", "csv", "--sort-by", "objectId", "datastore", "config-state", "list", "--config-id", f"{CONFIG_ID}"]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_3
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_4
		assert stdout_into_list(_stdout)[3][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[4][0] == CLIENT_ID_2
		assert len(stdout_into_list(_stdout)) - 1 == 4

		# All objectId's (2), all configId's
		exit_code, _stdout, _stderr = run_cli(["--output-format", "csv", "datastore", "config-state", "list"])
		assert exit_code == 0
		assert len(stdout_into_list(_stdout)) - 1 == 4 * len(all_configs)

		# (SERVER)
		# test if the origin and changed value of a config is shown correctly
		# opsi.check.enabled: False("0") -> True("1")
		# configs for DEPOT
		CONFIGSTATE_1_DEPOT = {"configId": f"{CONFIG_ID}", "objectId": f"{DEPOT_ID}", "values": False}
		CONFIGSTATE_2_DEPOT = {"configId": f"{CONFIG_ID}", "objectId": f"{DEPOT_ID}", "values": True}

		admin_service_client.jsonrpc("configState_createObjects", params=[CONFIGSTATE_1_DEPOT])  # type:ignore[attr-defined]
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"config-state",
				"list",
				"--object-id",
				f"{CLIENT_ID_1}",
				"--config-id",
				f"{CONFIG_ID}",
			]
		)
		assert exit_code == 0
		assert (
			stdout_into_list(_stdout)[1][2] == "0"
		)  # only second row is of interest, first row of stdout_list[0][i]=([clientId, configId, value, origin])
		assert stdout_into_list(_stdout)[1][3] == "[yellow]server[/yellow]"

		admin_service_client.jsonrpc("configState_updateObjects", params=[CONFIGSTATE_2_DEPOT])  # type:ignore[attr-defined]
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"config-state",
				"list",
				"--object-id",
				f"{CLIENT_ID_1}",
				"--config-id",
				f"{CONFIG_ID}",
			]
		)
		assert exit_code == 0
		assert (
			stdout_into_list(_stdout)[1][2] == "1"
		)  # only second row is of interest, first row of stdout_list[0][i]=([clientId, configId, value, origin])
		assert stdout_into_list(_stdout)[1][3] == "[yellow]server[/yellow]"

		# (CLIENT)
		# test if the origin and changed value of a config is shown correctly
		# opsi.check.enabled: True("1") -> False("0")
		# check if CLIENT overrides origin from server -> client
		# configs for CLIENT_1
		CONFIGSTATE_1_CLIENT_1 = {"configId": f"{CONFIG_ID}", "objectId": f"{CLIENT_ID_1}", "values": True}
		CONFIGSTATE_2_CLIENT_1 = {"configId": f"{CONFIG_ID}", "objectId": f"{CLIENT_ID_1}", "values": False}

		admin_service_client.jsonrpc("configState_createObjects", params=[CONFIGSTATE_1_CLIENT_1])  # type:ignore[attr-defined]
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"config-state",
				"list",
				"--object-id",
				f"{CLIENT_ID_1}",
				"--config-id",
				f"{CONFIG_ID}",
			]
		)
		assert exit_code == 0
		assert (
			stdout_into_list(_stdout)[1][2] == "1"
		)  # only second row is of interest, first row of stdout_list[0][i]=([clientId, configId, value, origin])
		assert stdout_into_list(_stdout)[1][3] == "[blue]client[/blue]"

		admin_service_client.jsonrpc("configState_updateObjects", params=[CONFIGSTATE_2_CLIENT_1])  # type:ignore[attr-defined]
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"datastore",
				"config-state",
				"list",
				"--object-id",
				f"{CLIENT_ID_1}",
				"--config-id",
				f"{CONFIG_ID}",
			]
		)
		assert exit_code == 0
		assert (
			stdout_into_list(_stdout)[1][2] == "0"
		)  # only second row is of interest, first row of stdout_list[0][i]=([clientId, configId, value, origin])
		assert stdout_into_list(_stdout)[1][3] == "[blue]client[/blue]"

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
				"--object-id",
				f"{CLIENT_ID_3},{CLIENT_ID_4}",
				"--config-id",
				f"{CONFIG_ID}",
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
				"--object-id",
				f"{CLIENT_ID_WILDCARD_1},{CLIENT_ID_WILDCARD_2}",
				"--config-id",
				f"{CONFIG_ID}",
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
				"--object-id",
				f"{CLIENT_ID_WILDCARD_1},{CLIENT_ID_WILDCARD_3}",
				"--config-id",
				f"{CONFIG_ID}",
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
				"--object-id",
				f"{CLIENT_ID_WILDCARD_1},{CLIENT_ID_WILDCARD_2},{CLIENT_ID_WILDCARD_3},{CLIENT_ID_WILDCARD_4}",
				"--config-id",
				f"{CONFIG_ID}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_3
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_4
		assert stdout_into_list(_stdout)[3][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[4][0] == CLIENT_ID_2
		assert len(stdout_into_list(_stdout)) - 1 == 4


# ===================================CONFIG-STATE SET TESTS============================================
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
		(UNICODE_CONFIG_MULTI, CLIENT_ID_1, ["a", "b", "c"], ["a", "b", "c"]),  # set Unicode MultiValue-> create configState
		(UNICODE_CONFIG_MULTI, CLIENT_ID_1, [], []),  # empty list for MultiValue-> create configState
		(UNICODE_CONFIG_MULTI, CLIENT_ID_2, ["a", "b", "d"], ["a", "b", "d"]),
		(UNICODE_CONFIG_MULTI, CLIENT_ID_1, ["d", "e", "f"], ["d", "e", "f"]),  # set Unicode MultiValue-> update configState
		(UNICODE_CONFIG_MULTI, CLIENT_ID_2, ["d", "e", "f"], ["d", "e", "f"]),
		(UNICODE_CONFIG_MULTI, "all", ["1", "2", "3"], ["1", "2", "3"]),  # set Unicode MultiValue-> objectId='all'
		(UNICODE_CONFIG_MULTI, "all", ["3", "4", "5"], ["3", "4", "5"]),
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
				exit_code, _stdout, _stderr = run_cli(["datastore", "config-state", "set"] + [config] + [object_id] + value_in)
				assert exit_code == 0
				assert admin_service_client.configState_getValues(config, [object_id])[object_id][config] == value_out  # type: ignore[attr-defined]
		else:
			exit_code, _stdout, _stderr = run_cli(
				[
					"datastore",
					"config-state",
					"set",
				]
				+ [config]
				+ [object_id]
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
		exit_code, _stdout, _stderr = run_cli(["datastore", "config-state", "set"] + [BOOL_CONFIG] + [CLIENT_ID_1] + ["test"])
		assert exit_code != 0
		assert f"'test' is not valid for {BOOL_CONFIG}." in _stderr
		assert "Possible values are: [False, True]" in _stderr

		# - bool config and multiple values
		exit_code, _stdout, _stderr = run_cli(["datastore", "config-state", "set"] + [BOOL_CONFIG] + [CLIENT_ID_1] + ["test", "testing"])
		assert exit_code != 0
		assert f"Multivalues are not valid for {BOOL_CONFIG}" in _stderr
		assert "Possible values are: [False, True]" in _stderr

		# - unicode config and multiple values
		exit_code, _stdout, _stderr = run_cli(["datastore", "config-state", "set"] + [UNICODE_CONFIG_ONE] + [CLIENT_ID_1] + ["g:", "h:"])
		assert exit_code != 0
		assert f"Value is not valid for {UNICODE_CONFIG_ONE}." in _stderr
		assert "Multivalues are not allowed." in _stderr

		# - unicode config and wrong value
		exit_code, _stdout, _stderr = run_cli(["datastore", "config-state", "set"] + [UNICODE_CONFIG_ONE] + [CLIENT_ID_1] + ["test"])
		assert exit_code != 0
		assert f"Value is not valid for {UNICODE_CONFIG_ONE}." in _stderr
		assert "Possible values are:" in _stderr


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
		unlock_products(["gimp2", "test2", "pytest-product1", "pytest-product2", "opsi-client-agent"])
		verify_lock_status(admin_service_client, is_locked=False)


# lock product (failed installation) -> verify -> unlock (CLI) -> verify
@pytest.mark.opsi_service
def test_product_unlock_installation(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		install_broken_package()
		verify_lock_status(admin_service_client, is_locked=True, product_id="gimp2")
		unlock_products(product_id=["gimp2"])
		verify_lock_status(admin_service_client, is_locked=False)


# lock products -> verify -> try unlock (wrong/mutliple depot-ids) -> verify error message
@pytest.mark.opsi_service
def test_wrong_depot_id(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		lock_products(admin_service_client)
		verify_lock_status(admin_service_client, is_locked=True)
		exitcode, _stdout, stderr = unlock_products(depot_id=["hallo,test"])
		assert exitcode != 0
		assert "No such depot(s)" in stderr
