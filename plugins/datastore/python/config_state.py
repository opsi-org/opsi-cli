# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from typing import Any

import rich_click as click
from opsi.logging import get_logger
from opsi.opsi.service.model.object import Config, ConfigState

from opsicli.decorators import dry_run_capable, mutually_exclusive
from opsicli.io import Metadata, OutputType, console_print, write_output
from opsicli.opsiservice import ServiceClient, config, get_service_connection
from plugins.datastore.data.help_texts import CONFIG_STATE_HELP as info
from plugins.datastore.data.messages import Error, Status

from .common import (
	cli,
	create_client_depot_mapping,
	process_set,
	process_where,
	validate_against_possible_values,
)
from .metadata import COMMAND_METADATA

logger = get_logger("opsicli")


def _get_default_config_states(
	service_connection: ServiceClient, object_ids: str | list[str], config_ids: str | list[str], filter: dict[str, str | list[str]]
) -> dict[str, dict[str, dict[str, Any]]]:
	bool_attr = [filter.pop("multiValue", None), filter.pop("editable", None)]
	normalized_bool_attr = [
		True if value in ("True", "true", "1") else False if value in ("False", "false", "0") else None for value in bool_attr
	]

	default_config_objects = service_connection.config_getObjects(  # ty: ignore[unresolved-attribute]
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
	depot_ids: str | list[str],
	config_ids: str | list[str],
	default_states: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:

	depot_config_states = service_connection.configState_getObjects(objectId=depot_ids, configId=config_ids)  # ty: ignore[unresolved-attribute]

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
	object_ids: str | list[str],
	config_ids: str | list[str],
	depot_states: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:

	client_config_states = service_connection.configState_getObjects(objectId=object_ids, configId=config_ids)  # ty: ignore[unresolved-attribute]

	for state in client_config_states:
		if state.objectId in depot_states and state.configId in depot_states[state.objectId]:
			target = depot_states[state.objectId][state.configId]
			target["clientValues"] = state.values
			target["origin"] = "client"
			if target["defaultValues"] != state.values:
				target["values"] = state.values

	return depot_states


def _update_database(data: list[dict[str, str | list[Any]]], config_states: list[ConfigState], metadata: Metadata) -> None:
	service_connection = get_service_connection()

	if not config.dry_run:
		service_connection.configState_updateObjects(config_states)  # ty: ignore[unresolved-attribute]
		msg = Status.success()
	else:
		msg = Status.dry_run()

	console_print(msg, style="green", output_type=OutputType.MESSAGE)
	write_output(data=sorted(data, key=lambda x: x["objectId"]), metadata=metadata)


def _create_output_data(
	config_obj: Config, config_states: list[ConfigState], current_values: dict[str, dict[str, str]]
) -> list[dict[str, str | list[Any]]]:
	updated_data: list[dict[str, str | list[Any]]] = []
	for state in config_states:
		updated_data.append(
			{
				"objectId": state.objectId,
				"configId": state.configId,
				"possibleValues": config_obj.possibleValues or [],
				"previousValues": current_values[state.objectId][state.configId],
				"values": state.values or [],
			}
		)
	return updated_data


def _create_config_states(object_ids: list[str], config_id: str, values: list[str] | list[bool]) -> list[ConfigState]:
	config_states = []

	for obj_id in object_ids:
		config_state = ConfigState(configId=config_id, objectId=obj_id, values=values)
		config_states.append(config_state)
	return config_states


def _fetch_and_filter_config_states(where: tuple[str, ...], all_flag: bool, no_defaults: bool | None = None) -> list[dict[str, Any]]:
	service_connection = get_service_connection()
	attributes = COMMAND_METADATA["datastore_config-state_list"].attributes

	filter: dict[str, str | list[str]] = {}
	if not all_flag:
		filter = process_where(where, attributes=attributes)

	object_ids = service_connection.host_getIdents(id=filter.get("objectId", None))  # ty: ignore[unresolved-attribute]
	if not object_ids:
		raise ValueError(f"No clients found matching the supplied objectId filter: {filter['objectId']}.")
	config_ids = service_connection.config_getIdents(id=filter.get("configId", None))  # ty: ignore[unresolved-attribute]
	depot_ids = service_connection.host_getIdents(type="OpsiDepotServer")  # ty: ignore[unresolved-attribute]

	if not (object_ids and config_ids):
		raise ValueError(Error.no_match())

	client_to_depot = create_client_depot_mapping(service_connection)
	default_states = _get_default_config_states(service_connection, object_ids, config_ids, filter)
	depot_states = _update_default_states(service_connection, client_to_depot, depot_ids, config_ids, default_states)
	client_states = _update_depot_states(service_connection, object_ids, config_ids, depot_states)

	flattened_list = [config_state for config_map in client_states.values() for config_state in config_map.values()]

	# result = filter_by_attribute_values(data=flattened_list, attributes=attributes, filter=filter)

	if no_defaults:
		flattened_list = [entry for entry in flattened_list if entry.get("origin") != "default"]

	return flattened_list


@cli.group(name="config-state", short_help=info.GENERAL.short, help=info.GENERAL.long)
def config_state() -> None:
	pass


@config_state.command(name="list", help=info.LIST.long, short_help=info.LIST.short)
@click.option("--where", type=str, multiple=True, help=info.LIST.where)
@click.option(
	"--all",
	is_flag=True,
	help=info.LIST.all,
)
@dry_run_capable
@mutually_exclusive("where", "all")
def list_config_state(where: tuple[str, ...], all: bool) -> None:
	result = _fetch_and_filter_config_states(where, all_flag=all)

	write_output(
		data=sorted(result, key=lambda x: x["objectId"]),
		metadata=COMMAND_METADATA["datastore_config-state_list"],
		value_styles={"depot": "yellow", "client": "blue"},
	)


@config_state.command(name="update", short_help=info.UPDATE.short, help=info.UPDATE.long)
@click.option("--where", type=str, multiple=True, help=info.UPDATE.where)
@click.option(
	"--set",
	type=str,
	multiple=True,
	help=info.UPDATE.set,
)
@dry_run_capable
def update_config_state(where: tuple[str, ...], set: tuple[str, ...]) -> None:
	service_connection = get_service_connection()
	metadata = COMMAND_METADATA["datastore_config-state_update"]
	attributes = metadata.attributes
	attributes_where = attributes[:2]  # objectId, configId
	attributes_set = attributes[-1:]  # values

	filter = process_where(where, attributes=attributes_where, operation="update")
	updates = process_set(set, attributes=attributes_set)

	# Get separated IDs from filter
	object_ids = service_connection.host_getIdents(id=filter.get("objectId", None))  # ty: ignore[unresolved-attribute]
<<<<<<< HEAD
	if not object_ids:
		raise ValueError(f"No clients found matching the supplied objectId filter: {filter['objectId']}.")
=======
>>>>>>> 338d3da87e31c2d0286fa05770afc733c2b13ae0

	config_id = filter.get("configId", None)

	if not isinstance(config_id, str):
		raise ValueError("Only one configId without wildcard is allowed.")
	else:
		config_obj = service_connection.config_getObjects(id=config_id)[0]  # ty: ignore[unresolved-attribute]

	# Validate values
	validated_values = validate_against_possible_values(updates["values"], config_obj)
	current_values = service_connection.configState_getValues(config_id, object_ids)  # ty: ignore[unresolved-attribute]

	# Create config-state objects
	updated_config_states = _create_config_states(object_ids, config_id, validated_values)

	# Empty result
	if not updated_config_states:
		raise ValueError(Error.no_match())

	output_data = _create_output_data(config_obj, updated_config_states, current_values)
	_update_database(output_data, updated_config_states, metadata)


@config_state.command(name="delete", short_help=info.DELETE.short, help=info.DELETE.long)
@click.option(
	"--where",
	type=str,
	multiple=True,
	help=info.DELETE.where,
)
@dry_run_capable
def delete_config_state(
	where: tuple[str, ...],
) -> None:
	service_connection = get_service_connection()
	metadata = COMMAND_METADATA["datastore_config-state_delete"]
	filter = process_where(where, attributes=metadata.attributes, operation="delete")

	result = _fetch_and_filter_config_states(where, all_flag=False, no_defaults=True)
	if not result:
		raise ValueError(Error.no_match())

	if config.dry_run:
		msg = Status.dry_run()
	else:
		msg = Status.success()

	console_print(msg, style="green", output_type=OutputType.MESSAGE)

	if result:
		write_output(
			data=sorted(result, key=lambda x: x["objectId"]),
			metadata=COMMAND_METADATA["datastore_config-state_list"],
			value_styles={"depot": "yellow", "client": "blue"},
		)

	if not config.dry_run:
		service_connection.configState_delete(objectId=filter.pop("objectId"), configId=filter.pop("configId"))  # ty: ignore[unresolved-attribute]
