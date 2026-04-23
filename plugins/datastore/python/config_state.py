# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only
from typing import Any

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.objects import Config, ConfigState

from opsicli.decorators import dry_run_capable
from opsicli.io import Metadata, OutputType, console_print, get_separated_entries, write_output
from opsicli.opsiservice import ServiceClient, config, get_service_connection

from .common import (
	cli,
	create_client_depot_mapping,
	filter_by_attributes,
	process_set,
	process_where,
	validate_against_possible_values,
)
from .metadata import COMMAND_METADATA

logger = get_logger("opsicli")


def _get_default_config_states(
	service_connection: ServiceClient, object_ids: list[str], config_ids: list[str], filter: dict[str, str]
) -> dict[str, dict[str, dict[str, Any]]]:
	bool_attr = [filter.pop("multiValue", None), filter.pop("editable", None)]
	normalized_bool_attr = [
		True if value in ("True", "true", "1") else False if value in ("False", "false", "0") else None for value in bool_attr
	]

	default_config_objects = service_connection.config_getObjects(  # type: ignore[attr-defined]
		id=config_ids,
		type=filter.pop("type", None),
		description=filter.pop("description", None),
		multiValue=normalized_bool_attr[0],  # focreBool() is not enough; every string that is not empty will be true
		editable=normalized_bool_attr[1],  # 							""
		value=filter.pop("defaultValues", None),
	)

	default_states = {}
	for object_id in object_ids:
		default_states[object_id] = {}
		for entry in default_config_objects:
			default_states[object_id][entry.id] = {
				"objectId": object_id,
				"configId": entry.id,
				"description": entry.description,
				"multiValue": entry.multiValue,
				"editable": entry.editable,
				"values": entry.defaultValues,
				"possibleValues": entry.possibleValues,
				"defaultValues": entry.defaultValues,
				"depotValues": "",
				"clientValues": "",
				"origin": "default",
				"depotId": "",
			}
	return default_states


def _update_default_states(
	service_connection: ServiceClient,
	client_to_depot: dict[str, str],
	depot_ids: list[str],
	config_ids: list[str],
	default_states: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:

	depot_config_states = service_connection.configState_getObjects(objectId=depot_ids, configId=config_ids)  # type: ignore[attr-defined]

	# account for different depots
	depot_lookup = {(s.objectId, s.configId): s.values for s in depot_config_states}

	for object_id, config_id_dict in default_states.items():
		assigned_depot_id = client_to_depot.get(object_id)
		if not assigned_depot_id:
			continue

		for config_id, default_state in config_id_dict.items():
			default_state["depotId"] = assigned_depot_id
			if (assigned_depot_id, config_id) in depot_lookup:
				depot_values = depot_lookup[(assigned_depot_id, config_id)]
				default_state["depotValues"] = depot_values
				default_state["origin"] = "depot"
				if default_state["defaultValues"] != depot_values:
					default_state["values"] = depot_values

	return default_states


def _update_depot_states(
	service_connection: ServiceClient,
	object_ids: list[str],
	config_ids: list[str],
	depot_states: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:

	client_config_states = service_connection.configState_getObjects(objectId=object_ids, configId=config_ids)  # type: ignore[attr-defined]

	for state in client_config_states:
		if state.objectId in depot_states and state.configId in depot_states[state.objectId]:
			target = depot_states[state.objectId][state.configId]
			target["clientValues"] = state.values
			target["origin"] = "client"
			if target["defaultValues"] != state:
				target["values"] = state.values

	return depot_states


def _update_database(data: list[dict[str, str]], config_states: list[ConfigState], metadata: Metadata) -> None:
	service_connection = get_service_connection()

	if config.dry_run:
		msg = "Update skipped due to dry run. Here are the clients that would have been updated:\n"
	else:
		msg = "Config-state updated successfully. Here are the updated clients."
		service_connection.configState_updateObjects(config_states)  # type: ignore[attr-defined]

	console_print(msg, style="green", output_type=OutputType.MESSAGE)
	write_output(data=sorted(data, key=lambda x: x["objectId"]), metadata=metadata)


def _create_output_data(
	config_obj: Config, config_states: list[ConfigState], current_values: dict[str, dict[str, str]]
) -> list[dict[str, str]]:
	updated_data = []
	for state in config_states:
		updated_data.append(
			{
				"objectId": state.objectId,
				"configId": state.configId,
				"possibleValues": config_obj.possibleValues,
				"previousValues": current_values[state.objectId][state.configId],
				"values": state.values,
			}
		)
	return updated_data


def _create_config_states(object_ids: list[str], config_id: str, values: list[str] | list[bool]) -> list[ConfigState]:
	config_states = []

	for obj_id in object_ids:
		config_state = ConfigState(configId=config_id, objectId=obj_id, values=values)
		config_states.append(config_state)
	return config_states


@cli.group(name="config-state", short_help="Manage configuration states of clients.")
def config_state() -> None:
	"""
	View and chnage configuration states of clients.
	"""
	pass


@config_state.command(name="list", short_help="List configuration states of clients.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter config-states.",
)
@dry_run_capable
def list_config_state(where: tuple[str, ...]) -> None:
	"""
	List all configuration states or apply filters to narrow the results.
	"""

	service_connection = get_service_connection()
	metadata = COMMAND_METADATA["datastore_config-state_list"]
	attributes = metadata.attributes

	filter = process_where(where, attributes=attributes)

	# process wildcards
	filter = {k: (v if v != "*" else None) for k, v in filter.items()}

	# get separated Id's from filter
	final_object_ids = service_connection.host_getIdents(id=get_separated_entries(filter.pop("objectId", None)))  # type: ignore[attr-defined]
	final_config_ids = get_separated_entries(filter.pop("configId", None))
	final_depot_ids = service_connection.host_getIdents(type="OpsiDepotServer")  # type: ignore[attr-defined]

	# get a client to depot mapping
	client_to_depot = create_client_depot_mapping(service_connection)

	# get default states and upfate them
	default_states = _get_default_config_states(service_connection, final_object_ids, final_config_ids, filter)
	depot_states = _update_default_states(service_connection, client_to_depot, final_depot_ids, final_config_ids, default_states)
	client_states = _update_depot_states(service_connection, final_object_ids, final_config_ids, depot_states)

	# prepare data for writing output (flattened list)
	flattened_list = [
		config_state
		for config_map in client_states.values()  # objcects
		for config_state in config_map.values()  # configs
	]

	result = filter_by_attributes(data=flattened_list, attributes=attributes, filter=filter)

	# empty result
	if not result:
		raise ValueError("No config-states found matching the filtering criteria.")

	write_output(
		data=sorted(result, key=lambda x: x["objectId"]),
		metadata=metadata,
		value_styles={"depot": "yellow", "client": "blue"},
	)


@config_state.command(
	name="update",
	short_help="Update a configuration state for one or multiple clients.",
)
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter config-states.",
)
@click.option(
	"--set",
	type=str,
	multiple=True,
	help="Set value(s) of the config-state.",
)
@dry_run_capable
def update_config_state(where: tuple[str, ...], set: tuple[str, ...]) -> None:
	"""
	Update a configuration state for one or multiple clients.
	"""

	service_connection = get_service_connection()
	metadata = COMMAND_METADATA["datastore_config-state_update"]
	attributes = metadata.attributes
	attributes_where = attributes[:2]  # objectId, configId
	attributes_set = attributes[-1:]  # values

	filter = process_where(where, attributes=attributes_where, operation="update")
	# process wildcards
	filter = {k: (v if v != "*" else None) for k, v in filter.items()}

	updates = process_set(set, attributes=attributes_set)

	# get separated Id's from filter
	object_ids = service_connection.host_getIdents(id=get_separated_entries(filter["objectId"]) if filter["objectId"] != "*" else None)  # type: ignore[attr-defined]
	config_id = get_separated_entries(filter["configId"])

	if len(config_id) > 1 or "*" in config_id:
		raise ValueError("Only one configId without wildcard is allowed.")

	config_obj = service_connection.config_getObjects(id=config_id[0])  # type: ignore[attr-defined]

	# validate values
	validated_values = validate_against_possible_values(updates["values"], config_obj[0])
	current_values = service_connection.configState_getValues(config_id, object_ids)  # type: ignore[attr-defined]

	# create config-state objects
	updated_config_states = _create_config_states(object_ids, config_obj[0].id, validated_values)

	# empty result
	if not updated_config_states:
		raise ValueError("No config-states found matching the filtering criteria.")

	output_data = _create_output_data(config_obj[0], updated_config_states, current_values)
	_update_database(output_data, updated_config_states, metadata)
