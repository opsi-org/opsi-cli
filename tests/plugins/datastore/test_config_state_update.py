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
		# BoolConfig // one objectId, one configId
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[0].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
				"--set",
				"values=false",
			],
			[
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[0].id,
					"previousValues": "1",
					"values": "0",
				},
			],
			[
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[0].id,
					"values": [False],
				},
			],
			None,
		),
		# BoolConfig // multiple objectId's, one configId
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[0].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}, {TEST_CLIENTS[1].id}",
				"--set",
				"values=true",
			],
			[
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[0].id,
					"previousValues": "1",
					"values": "1",
				},
				{
					"objectId": TEST_CLIENTS[1].id,
					"configId": TEST_CONFIGS[0].id,
					"previousValues": "1",
					"values": "1",
				},
			],
			[
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[0].id,
					"values": [True],
				},
				{
					"objectId": TEST_CLIENTS[1].id,
					"configId": TEST_CONFIGS[0].id,
					"values": [True],
				},
			],
			None,
		),
		# BoolConfig // all objectId's, one configId
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[0].id}",
				"--where",
				"objectId=*",
				"--set",
				"values=false",
			],
			[
				{
					"objectId": "opsi.opsi.test",
					"configId": TEST_CONFIGS[0].id,
					"previousValues": "1",
					"values": "0",
				},
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[0].id,
					"previousValues": "1",
					"values": "0",
				},
				{
					"objectId": TEST_CLIENTS[1].id,
					"configId": TEST_CONFIGS[0].id,
					"previousValues": "1",
					"values": "0",
				},
			],
			[
				{
					"objectId": "opsi.opsi.test",
					"configId": TEST_CONFIGS[0].id,
					"values": [False],
				},
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[0].id,
					"values": [False],
				},
				{
					"objectId": TEST_CLIENTS[1].id,
					"configId": TEST_CONFIGS[0].id,
					"values": [False],
				},
			],
			None,
		),
		# BoolConfig // multiple --where objectId=...
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[0].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
				"--where",
				f"objectId={TEST_CLIENTS[1].id}",
				"--set",
				"values=false",
			],
			[
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[0].id,
					"previousValues": "1",
					"values": "0",
				},
				{
					"objectId": TEST_CLIENTS[1].id,
					"configId": TEST_CONFIGS[0].id,
					"previousValues": "1",
					"values": "0",
				},
			],
			[
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[0].id,
					"values": [False],
				},
				{
					"objectId": TEST_CLIENTS[1].id,
					"configId": TEST_CONFIGS[0].id,
					"values": [False],
				},
			],
			None,
		),
		# UnicodeConfig // one objectId, one configId
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[1].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
				"--set",
				"values=test",
			],
			[
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[1].id,
					"previousValues": "windomain",
					"values": "test",
				},
			],
			[
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[1].id,
					"values": ["test"],
				},
			],
			None,
		),
		# UnicodeConfig // multiple objectId's, one configId
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[1].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}, {TEST_CLIENTS[1].id}",
				"--set",
				"values=test, test",
			],
			[
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[1].id,
					"previousValues": "windomain",
					"values": "test,test",
				},
				{
					"objectId": TEST_CLIENTS[1].id,
					"configId": TEST_CONFIGS[1].id,
					"previousValues": "windomain",
					"values": "test,test",
				},
			],
			[
				{
					"objectId": TEST_CLIENTS[0].id,
					"configId": TEST_CONFIGS[1].id,
					"values": ["test", "test"],
				},
				{
					"objectId": TEST_CLIENTS[1].id,
					"configId": TEST_CONFIGS[1].id,
					"values": ["test", "test"],
				},
			],
			None,
		),
		# ERRORS
		# BoolConfig // wrong value
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[0].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
				"--set",
				"values=wrong",
			],
			None,
			None,
			("Possible values for:"),
		),
		# BoolConfig // multiple values
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[0].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
				"--set",
				"values=wrong, more_wrong",
			],
			None,
			None,
			("Only one value is allowed for:", "Possible values are:"),
		),
		# UnicodeConfig // wrong value
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[1].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
				"--set",
				"values=wrong",
			],
			None,
			None,
			("Possible values for:"),
		),
		# UnicodeConfig // not multiValue
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[2].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
				"--set",
				"values=bonidepot.uib.local, bonifax.uib.local",
			],
			None,
			None,
			("MultiValues are not allowed for:", "Possible values are:"),
		),
		# Missing configId
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
				"--set",
				"values=wrong",
			],
			None,
			None,
			(
				"Incomplete filter for update operation.",
				"If you intentionally do not want to filter by an attribute",
				"On update operations, the filter must contain all identifier attributes.",
				"Missing required attributes: configId",
			),
		),
		# Missing objectId
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[0].id}",
				"--set",
				"values=wrong",
			],
			None,
			None,
			(
				"Incomplete filter for update operation.",
				"If you intentionally do not want to filter by an attribute",
				"On update operations, the filter must contain all identifier attributes.",
				"Missing required attributes: objectId",
			),
		),
		# Missing --where
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--set",
				"values=wrong",
			],
			None,
			None,
			(
				"Incomplete filter for update operation.",
				"If you intentionally do not want to filter by an attribute",
				"Available attributes are:",
				"objectId",
				"The ID of the object (host)",
				"configId",
				"The ID of the config-state.",
				"Missing required attributes: objectId, configId",
			),
		),
		# Missing --set
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"update",
				"--where",
				f"configId={TEST_CONFIGS[1].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
			],
			None,
			None,
			(
				"No attributes specified to update.",
				"Available attributes are:",
				"values  (str | bool)  The current effective value for this state.",
			),
		),
	),
)
def test_config_state_update(
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

		states = admin_service_client.configState_getObjects(configId=config_id, objectId=object_id)  # type: ignore[attr-defined]
		if expected_output and config_id and object_id:
			for state, expect in zip(states, expected_values):
				assert state.__dict__ == expect
