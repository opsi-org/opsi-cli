# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only
from typing import Any

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.objects import Config, ConfigState
from opsicommon.types import forceBool

from opsicli.decorators import dry_run_capable
from opsicli.io import OutputType, console_print, write_output
from opsicli.opsiservice import config, get_service_connection

from .common import (
	cli,
	filter_by_attributes,
	get_validated_ids,
	process_set,
	process_where,
	validate_against_possible_values,
)
from .metadata import COMMAND_METADATA

logger = get_logger("opsicli")


@cli.group(name="config-state", short_help="Configure config states.")
def config_state() -> None:
	"""
	View and manage config states.
	"""
	pass


@config_state.command(name="list", short_help="List all config states or apply filters to narrow the results.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter the output. ObjectId and ConfigId are required",
)
def list_config_state(where: tuple[str, ...]) -> None:
	"""
	View all configuration states or apply filters to narrow your search.
	"""

	def _get_default_config_states(object_ids: list[str], config_ids: list[str] | None) -> dict[str, dict[str, dict[str, Any]]]:
		default_config_objects = service_connection.config_getObjects(  # type: ignore[attr-defined]
			id=config_ids or [],
			type=filter.pop("type", None),
			description=filter.pop("description", None),
			multiValue=forceBool(v) if (v := filter.pop("multiValue", None)) is not None else None,
			editable=forceBool(v) if (v := filter.pop("editable", None)) is not None else None,
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
				}
		return default_states

	def _update_default_states(
		depot_ids: list[str],
		config_ids: list[str] | None,
		default_states: dict[str, dict[str, dict[str, Any]]],
	) -> dict[str, dict[str, dict[str, Any]]]:
		depot_config_states = service_connection.configState_getObjects(  # type: ignore[attr-defined]
			objectId=depot_ids, configId=config_ids or []
		)
		for state in depot_config_states:
			if state.objectId in default_states and state.configId in default_states[state.objectId]:
				target = default_states[state.objectId][state.configId]
				target["depotValues"] = state.values
				target["origin"] = "depot"
				if target["defaultValues"] != state.values:
					target["values"] = state.values

		return default_states

	def _update_depot_states(
		object_ids: list[str],
		config_ids: list[str] | None,
		depot_states: dict[str, dict[str, dict[str, Any]]],
	) -> dict[str, dict[str, dict[str, Any]]]:
		client_config_state_objects = service_connection.configState_getObjects(  # type: ignore[attr-defined]
			objectId=object_ids, configId=config_ids or []
		)

		for state in client_config_state_objects:
			if state.objectId in depot_states and state.configId in depot_states[state.objectId]:
				target = depot_states[state.objectId][state.configId]
				target["clientValues"] = state.values
				target["origin"] = "client"
				if target["defaultValues"] != state:
					target["values"] = state.values

		return depot_states

	service_connection = get_service_connection()
	metadata = COMMAND_METADATA["datastore_config-state_list"]
	attributes = metadata.attributes

	filter = process_where(where, attributes=attributes, operation="list")

	object_ids = filter.pop("objectId", "*")
	config_ids = filter.pop("configId", "*")

	final_object_ids = get_validated_ids(
		service_connection, ids=object_ids, type="objectId or depotId" if object_ids != "*" else "objectId"
	)
	final_config_ids = get_validated_ids(service_connection, ids=config_ids, type="configId")
	final_depot_ids = service_connection.host_getIdents(type="OpsiDepotServer")  # type: ignore[attr-defined]

	default_states = _get_default_config_states(final_object_ids, final_config_ids)
	depot_states = _update_default_states(final_depot_ids, final_config_ids, default_states)
	client_states = _update_depot_states(final_object_ids, final_config_ids, depot_states)

	flattened_result = [
		config_state
		for config_map in client_states.values()  # objcects
		for config_state in config_map.values()  # configs
	]
	filtered_data = filter_by_attributes(data=flattened_result, attributes=attributes, filter=filter)

	# select attributes to display
	for attr in attributes:
		if attr.id in ("objectId", "configId", "values", "origin"):
			attr.selected = True

	write_output(
		data=filtered_data,
		metadata=metadata,
		value_styles={"depot": "yellow", "client": "blue"},
	)


@config_state.command(
	name="update",
	short_help="Update an existing config state or create a new one if it doesn't exist. Using 'all' or '*' as the object ID will apply the value to all objects.",
)
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter config-states with objectId(s) and configId.",
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
	Change values of config states.
	"""

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
					"old": current_values[state.objectId][state.configId],
					"new": state.values,
				}
			)
		return sorted(updated_data, key=lambda x: x["objectId"])

	def _update_database(data: list[dict[str, str]], config_states: list[ConfigState], current_values: dict[str, dict[str, str]]) -> None:
		service_connection = get_service_connection()

		if config.dry_run:
			msg = "Update skipped due to dry run. Here are the clients that would have been updated:\n"
		else:
			msg = "Config-state updated successfully. Here are the updated clients."
			service_connection.configState_updateObjects(config_states)  # type: ignore[attr-defined]

		console_print(msg, style="green", output_type=OutputType.MESSAGE)
		write_output(data=data, metadata=COMMAND_METADATA.get("datastore_config-state_update"))

	def _create_config_states(object_ids: list[str], config_id: str, values: list[str] | list[bool]) -> list[ConfigState]:
		config_states = []

		for obj_id in object_ids:
			config_state = ConfigState(configId=config_id, objectId=obj_id, values=values)
			config_states.append(config_state)
		return config_states

	service_connection = get_service_connection()
	metadata = COMMAND_METADATA["datastore_config-state_update"]
	attributes = metadata.attributes

	# select attributes to display
	for attr in attributes:
		if attr.id in ("objectId", "configId", "possibleValues", "old", "new"):
			attr.selected = True

	filter = process_where(where, attributes=attributes, operation="update")
	updates = process_set(set, attributes=COMMAND_METADATA["set"].attributes)

	object_ids = get_validated_ids(service_connection, ids=filter["objectId"], type="objectId")
	config_id = get_validated_ids(service_connection, ids=filter["configId"], type="configId")
	if len(config_id) > 1:
		raise ValueError("Only one configId without wildcard is allowed.")
	config_obj = service_connection.config_getObjects(id=config_id)  # type: ignore[attr-defined]

	values = validate_against_possible_values(updates["values"], config_obj[0])
	current_values = service_connection.configState_getValues(config_id, object_ids)  # type: ignore[attr-defined]

	new_config_states = _create_config_states(object_ids, config_obj[0].id, values)
	output_data = _create_output_data(config_obj[0], new_config_states, current_values)
	_update_database(output_data, new_config_states, current_values)
