# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from opsi.opsi.service.client import ServiceClient
from opsi.opsi.service.model.object import BoolConfig, ConfigState, OpsiClient, UnicodeConfig

from opsicli.io import read_input_csv
from plugins.datastore.python.config_state import _fetch_and_filter_config_states, update_config_state
from tests.utils import assert_error_contains, get_depot_id, run_cli, tmp_clients, tmp_config_states, tmp_configs

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


def test_config_state_list_unmatched_object_id_stops_before_unfiltered_rpcs() -> None:
	service_client = MagicMock()
	service_client.host_getIdents.return_value = []

	with patch("plugins.datastore.python.config_state.get_service_connection", return_value=service_client):
		with pytest.raises(ValueError, match="No clients found matching the supplied objectId filter"):
			_fetch_and_filter_config_states(("objectId=nonexistent.test.invalid",), all_flag=False)

	service_client.config_getObjects.assert_not_called()
	service_client.configState_getObjects.assert_not_called()


def test_config_state_update_unmatched_object_id_stops_before_unfiltered_rpcs() -> None:
	service_client = MagicMock()
	service_client.host_getIdents.return_value = []

	with patch("plugins.datastore.python.config_state.get_service_connection", return_value=service_client):
		with pytest.raises(ValueError, match="No clients found matching the supplied objectId filter"):
			update_config_state.callback(("objectId=nonexistent.test.invalid", "configId=opsi.check.enabled"), ("values=true",))  # ty: ignore[call-non-callable]

	service_client.config_getObjects.assert_not_called()
	service_client.configState_getValues.assert_not_called()


def _values_to_str(values: str | bool | list[Any] | None) -> str:

	if isinstance(values, bool):
		return "1" if values else "0"
	if isinstance(values, list):
		processed = [("1" if v is True else "0" if v is False else str(v)) for v in values]
		return ", ".join(processed)
	if not values:
		return ""
	return values


@pytest.mark.opsi_service
@pytest.mark.parametrize(
	"command, expected_output, expected_values, expected_error",
	(
		# one objectId, one configId
		(
			# COMMAND
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
			# EXPECTED OUTPUT
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": _values_to_str(TEST_CONFIG_STATES[0].values),
					"origin": "client",
				},
			],
			# EXPECTED VALUES
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": TEST_CONFIG_STATES[0].values,
				},
			],
			# EXPECTED ERROR
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
					"values": _values_to_str(TEST_CONFIG_STATES[0].values),
					"origin": "client",
				},
				{
					"objectId": TEST_CONFIG_STATES[2].objectId,
					"configId": TEST_CONFIG_STATES[2].configId,
					"values": _values_to_str(TEST_CONFIG_STATES[2].values),
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
					"values": _values_to_str(TEST_CONFIG_STATES[0].values),
					"origin": "client",
				},
				{
					"objectId": TEST_CONFIG_STATES[1].objectId,
					"configId": TEST_CONFIG_STATES[1].configId,
					"values": _values_to_str(TEST_CONFIG_STATES[1].values),
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
					"values": _values_to_str(TEST_CONFIG_STATES[0].values),
					"origin": "client",
				},
				{
					"objectId": TEST_CONFIG_STATES[2].objectId,
					"configId": TEST_CONFIG_STATES[2].configId,
					"values": _values_to_str(TEST_CONFIG_STATES[2].values),
					"origin": "client",
				},
				{
					"objectId": "DEPOT_ID",
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": _values_to_str(TEST_CONFIG_STATES[0].values),
					"origin": "default",
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
		# more than one --where "objectId=..."
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
				f"objectId={TEST_CLIENTS[0].id}",
				"--where",
				f"objectId={TEST_CLIENTS[1].id}",
			],
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": _values_to_str(TEST_CONFIG_STATES[0].values),
					"origin": "client",
				},
				{
					"objectId": TEST_CONFIG_STATES[2].objectId,
					"configId": TEST_CONFIG_STATES[2].configId,
					"values": _values_to_str(TEST_CONFIG_STATES[2].values),
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
		# ERRORS
		# invalid objectId"
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
				"objectId=invalid",
			],
			[],
			[],
			("No clients found matching the supplied objectId filter: invalid.",),
		),
		# invalid configId"
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"list",
				"--where",
				"configId=invalid",
				"--where",
				f"objectId={TEST_CLIENTS[1].id}",
			],
			[],
			[],
			("No config-states found matching the filtering criteria.",),
		),
		# Missing objectId"
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"list",
				"--where",
				f"configId={TEST_CONFIG_STATES[0].configId}",
			],
			[
				{
					"objectId": "DEPOT_ID",
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": _values_to_str(TEST_CONFIG_STATES[0].values),
					"origin": "default",
				},
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": _values_to_str(TEST_CONFIG_STATES[0].values),
					"origin": "client",
				},
				{
					"objectId": TEST_CONFIG_STATES[2].objectId,
					"configId": TEST_CONFIG_STATES[2].configId,
					"values": _values_to_str(TEST_CONFIG_STATES[2].values),
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
		# process depot_id placeholders
		depot_id = get_depot_id(admin_service_client)
		for data_list in (expected_output, expected_values):
			for entry in data_list or []:
				if entry.get("objectId") == "DEPOT_ID":
					entry["objectId"] = depot_id

		exit_code, stdout, stderr = run_cli(command)
		if expected_output:
			expected_output = sorted(expected_output, key=lambda x: x["objectId"])
		if expected_values:
			expected_values = sorted(expected_values, key=lambda x: x["objectId"])
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
		states = admin_service_client.configState_getObjects(configId=config_id, objectId=object_id)  # ty: ignore[unresolved-attribute]
		if expected_output and config_id and object_id:
			for state, expect in zip(states, expected_values):
				assert state.__dict__ == expect


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
					"objectId": "DEPOT_ID",
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
					"objectId": "DEPOT_ID",
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
			("Invalid value `wrong` for the given"),
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
			("Multiple values `wrong, more_wrong`", "are not allowed", "BoolConfig:"),
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
				f"configId={TEST_CONFIGS[2].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
				"--set",
				"values=wrong",
			],
			None,
			None,
			("Invalid value `wrong` for the given"),
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
			("Multiple values `bonidepot.uib.local, bonifax.uib.local`", "are not allowed for the given UnicodeConfig:"),
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
				"Available attributes are:",
				"objectId",
				"The ID of the object",
				"configId",
				"The ID of the config",
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
		# process depot_id placeholders
		depot_id = get_depot_id(admin_service_client)
		for data_list in (expected_output, expected_values):
			for entry in data_list or []:
				if entry.get("objectId") == "DEPOT_ID":
					entry["objectId"] = depot_id
		if expected_output:
			expected_output = sorted(expected_output, key=lambda x: x["objectId"])
		if expected_values:
			expected_values = sorted(expected_values, key=lambda x: x["objectId"])
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

		states = admin_service_client.configState_getObjects(configId=config_id, objectId=object_id)  # ty: ignore[unresolved-attribute]
		if expected_output and config_id and object_id:
			for state, expect in zip(states, expected_values):
				assert state.__dict__ == expect


@pytest.mark.opsi_service
@pytest.mark.parametrize(
	"command, expected_output, expected_error",
	(
		# Case 1: Successful deletion.
		# A valid clientId and a valid configId are provided.
		(
			[
				"--sort-by",
				"objectId",
				"datastore",
				"config-state",
				"delete",
				"--where",
				f"configId={TEST_CONFIGS[0].id}",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
			],
			[
				{
					"objectId": TEST_CONFIG_STATES[0].objectId,
					"configId": TEST_CONFIG_STATES[0].configId,
					"values": _values_to_str(TEST_CONFIG_STATES[0].values),
					"origin": "client",
				},
			],
			None,
		),
		# Case 2: Validation Error - Missing objectId in filter.
		# The delete operation requires all identifier attributes according to process_where.
		(
			[
				"datastore",
				"config-state",
				"delete",
				"--where",
				f"configId={TEST_CONFIGS[0].id}",
			],
			None,
			("Incomplete filter for delete operation", "Missing required attributes: objectId"),
		),
		# Case 3: Validation Error - Missing configId in filter.
		# The delete operation requires all identifier attributes according to process_where.
		(
			[
				"datastore",
				"config-state",
				"delete",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
			],
			None,
			("Incomplete filter for delete operation", "Missing required attributes: configId"),
		),
		# Case 4: No Match Error - Filter criteria match non-existent data.
		# Ensuring that the command aborts correctly with a clear error message instead of failing silently.
		(
			[
				"datastore",
				"config-state",
				"delete",
				"--where",
				"configId=non.existent.config.id",
				"--where",
				f"objectId={TEST_CLIENTS[0].id}",
			],
			None,
			("No config-states found matching the filtering criteria.",),
		),
	),
)
def test_config_state_delete(
	admin_service_client: ServiceClient,
	command: list[str],
	expected_output: list[dict[str, str]] | None,
	expected_error: tuple[str, ...] | None,
) -> None:
	command = ["--output-format", "csv"] + command
	with (
		tmp_clients(admin_service_client, TEST_CLIENTS),
		tmp_configs(admin_service_client, TEST_CONFIGS),
		tmp_config_states(admin_service_client, TEST_CONFIG_STATES),
	):
		exit_code, stdout, stderr = run_cli(command)
		if expected_output:
			expected_output = sorted(expected_output, key=lambda x: x["objectId"])
		if expected_error:
			assert exit_code != 0
			assert_error_contains(stderr, expected_error)
		else:
			assert exit_code == 0
			data = read_input_csv(stdout.encode("utf-8"))
			assert data == expected_output
