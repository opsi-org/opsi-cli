# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import pytest
from opsicommon.client.opsiservice import ServiceClient
from opsicommon.objects import BoolConfig, ConfigState, OpsiClient, UnicodeConfig

from opsicli.io import read_input_csv
from tests.utils import assert_error_contains, run_cli, tmp_clients, tmp_config_states, tmp_configs

TEST_CLIENTS: list[OpsiClient] = [
	OpsiClient(id="pytest-client10.test.tld"),
	OpsiClient(id="pytest-client11.test.tld"),
]

TEST_CONFIGS: list[BoolConfig | UnicodeConfig] = [
	BoolConfig(
		id="opsi.check.enabled",
		description="Enable check",
		defaultValues=[True],
	),
	UnicodeConfig(
		id="opsi.check.ignore_products",
		description="",
		possibleValues=["windomain", "test"],
		defaultValues=["windomain"],
		editable=True,
		multiValue=True,
	),
	UnicodeConfig(
		id="clientdconfig.depot.id",
		description="ID of the OPSI depot to use",
		possibleValues=[
			"bonidepot.uib.local",
			"bonifax.uib.local",
			"bwfscdummydepot.uib.local",
			"docker-depot.uib.local",
			"dummy12x86.uib.local",
			"opsi.raspberry.local",
			"testdepotkk.uib.local",
			"tst-srv-002.uib.local",
			"tst-srv-003.uib.local",
			"tt-testdepot.uib.local",
			"vbrupertdepot1.uib.local",
			"vmex16205.uib.local",
		],
		defaultValues=["bonifax.uib.local"],
		editable=False,
		multiValue=False,
	),
]

TEST_CONFIG_STATES: list[ConfigState] = [
	ConfigState(
		objectId=TEST_CLIENTS[0].id,
		configId=TEST_CONFIGS[0].id,
		values=TEST_CONFIGS[0].defaultValues,
	),
	ConfigState(
		objectId=TEST_CLIENTS[0].id,
		configId=TEST_CONFIGS[1].id,
		values=TEST_CONFIGS[1].defaultValues,
	),
	ConfigState(
		objectId=TEST_CLIENTS[1].id,
		configId=TEST_CONFIGS[0].id,
		values=TEST_CONFIGS[0].defaultValues,
	),
	ConfigState(
		objectId=TEST_CLIENTS[1].id,
		configId=TEST_CONFIGS[1].id,
		values=TEST_CONFIGS[1].defaultValues,
	),
]


@pytest.mark.opsi_service
@pytest.mark.parametrize(
	"command, expected_output, expected_values, expected_error",
	(
		# one objectId, one configId
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"list",
				"--where",
				f"configId={TEST_CONFIGS[0].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
			],
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": ", ".join(str(v) if not isinstance(v, bool) else ("1" if v else "0") for v in TEST_CONFIG_STATES[0].values),
					"origin": "client",
				},
			],
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": TEST_CONFIG_STATES[0].values,
				},
			],
			None,
		),
		# multiple objectId's, one configId
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"list",
				"--where",
				f"configId={TEST_CONFIGS[0].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id},{TEST_CLIENTS[1].id}",
			],
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": ",".join(str(v) if not isinstance(v, bool) else ("1" if v else "0") for v in TEST_CONFIG_STATES[0].values),
					"origin": "client",
				},
				{
					"objectId": TEST_CONFIG_STATES[2].objectId,
					"configId": TEST_CONFIG_STATES[2].configId,
					"values": ", ".join(str(v) if not isinstance(v, bool) else ("1" if v else "0") for v in TEST_CONFIG_STATES[2].values),
					"origin": "client",
				},
			],
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": TEST_CONFIG_STATES[0].values,
				},
				{
					"objectId": TEST_CONFIG_STATES[2].objectId,
					"configId": TEST_CONFIG_STATES[2].configId,
					"values": TEST_CONFIG_STATES[2].values,
				},
			],
			None,
		),
		# one objectId, multiple configId's
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"list",
				"--where",
				f"configId={TEST_CONFIGS[0].id}, {TEST_CONFIGS[1].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
			],
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": ", ".join(str(v) if not isinstance(v, bool) else ("1" if v else "0") for v in TEST_CONFIG_STATES[0].values),
					"origin": "client",
				},
				{
					"objectId": TEST_CONFIG_STATES[1].objectId,
					"configId": TEST_CONFIG_STATES[1].configId,
					"values": ", ".join(str(v) if not isinstance(v, bool) else ("1" if v else "0") for v in TEST_CONFIG_STATES[1].values),
					"origin": "client",
				},
			],
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": TEST_CONFIG_STATES[0].values,
				},
				{
					"objectId": TEST_CONFIG_STATES[1].objectId,
					"configId": TEST_CONFIG_STATES[1].configId,
					"values": TEST_CONFIG_STATES[1].values,
				},
			],
			None,
		),
		# all objectId's, one configId
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"list",
				"--where",
				f"configId={TEST_CONFIG_STATES[0].configId}",
				"--where",
				"objectId=*",
			],
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": ", ".join(str(v) if not isinstance(v, bool) else ("1" if v else "0") for v in TEST_CONFIG_STATES[0].values),
					"origin": "client",
				},
				{
					"objectId": TEST_CONFIG_STATES[2].objectId,
					"configId": TEST_CONFIG_STATES[2].configId,
					"values": ", ".join(str(v) if not isinstance(v, bool) else ("1" if v else "0") for v in TEST_CONFIG_STATES[2].values),
					"origin": "client",
				},
			],
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": TEST_CONFIG_STATES[0].values,
				},
				{
					"objectId": TEST_CONFIG_STATES[2].objectId,
					"configId": TEST_CONFIG_STATES[2].configId,
					"values": TEST_CONFIG_STATES[2].values,
				},
			],
			None,
		),
	),
)
def test_config_state_list(
	admin_service_client: ServiceClient,
	command: list[str],
	expected_output: list[dict[str, str]] | None,
	expected_values: list[dict[str, str | None]],
	expected_error: tuple[str, ...] | None,
) -> None:
	command = ["--output-format", "csv"] + command
	with (
		tmp_clients(admin_service_client, TEST_CLIENTS),
		tmp_configs(admin_service_client, TEST_CONFIGS),
		tmp_config_states(admin_service_client, TEST_CONFIG_STATES),
	):
		exit_code, stdout, stderr = run_cli(command)
		if expected_error:
			assert exit_code != 0
			assert_error_contains(stderr, expected_error)
		else:
			assert exit_code == 0
			data = read_input_csv(stdout.encode("utf-8"))
			assert data == expected_output

		config_id = next((arg.split("=")[1] for arg in command if arg.startswith("configId=")), None)
		object_id = next((arg.split("=")[1] for arg in command if arg.startswith("objectId=")), None)

		config_id = [] if config_id == "*" else config_id
		object_id = [] if object_id == "*" else object_id
		states = admin_service_client.configState_getObjects(configId=config_id, objectId=object_id)  # type: ignore[attr-defined]
		if expected_output and config_id and object_id:
			for state, expect in zip(states, expected_values):
				assert state.__dict__ == expect
