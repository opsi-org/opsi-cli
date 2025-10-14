import pytest
from opsicommon.client.opsiservice import ServiceClient

from .utils import run_cli, tmp_client

CLIENT_ID_1 = "pytest-client1.test.tld"
CLIENT_ID_2 = "pytest-client2.test.tld"
CLIENT_ID_3 = "client3.test.tld"
CLIENT_ID_4 = "client4.test.tld"
CLIENT_ID_WILDCARD_1 = "py*"
CLIENT_ID_WILDCARD_2 = "cli*"
CLIENT_ID_WILDCARD_3 = "pyt*"
CLIENT_ID_WILDCARD_4 = "clie*"

CONFIG_ID = "opsi.check.enabled"


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


@pytest.mark.opsi_service
def test_config_state_list(admin_service_client: ServiceClient) -> None:
	with (
		tmp_client(admin_service_client, CLIENT_ID_1),
		tmp_client(admin_service_client, CLIENT_ID_2),
		tmp_client(admin_service_client, CLIENT_ID_3),
		tmp_client(admin_service_client, CLIENT_ID_4),
	):
		all_configs = admin_service_client.jsonrpc("config_getObjects", params=[])
		client_to_server_objects = admin_service_client.configState_getClientToDepotserver()
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

		admin_service_client.jsonrpc("configState_createObjects", params=[CONFIGSTATE_1_DEPOT])
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

		admin_service_client.jsonrpc("configState_updateObjects", params=[CONFIGSTATE_2_DEPOT])
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

		admin_service_client.jsonrpc("configState_createObjects", params=[CONFIGSTATE_1_CLIENT_1])
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

		admin_service_client.jsonrpc("configState_updateObjects", params=[CONFIGSTATE_2_CLIENT_1])
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
