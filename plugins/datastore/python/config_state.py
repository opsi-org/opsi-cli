# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only
from typing import Any

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.objects import Config, ConfigState

from opsicli.decorators import dry_run_capable
from opsicli.io import OutputType, console_print, get_separated_entries, write_output
from opsicli.opsiservice import config, get_service_connection

from .common import (
	cli,
	create_client_depot_mapping,
	filter_by_attributes,
	get_validated_object_ids,
	process_set,
	process_where,
	validate_against_possible_values,
)
from .metadata import COMMAND_METADATA, CONFIG_STATE_SET_METADATA, CONFIG_STATE_WHERE_METADATA

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
		default_config_objects = service_connection.config_getObjects(id=config_ids or [])  # type: ignore[attr-defined]
		default_states = {}
		for object_id in object_ids:
			default_states[object_id] = {}
			for entry in default_config_objects:
				default_states[object_id][entry.id] = {
					"values": entry.defaultValues,
					"default_values": entry.defaultValues,
					"depot_values": "",
					"client_values": "",
					"origin": "default",
					"configId": entry.id,
					"objectId": object_id,
				}
		return default_states

	def _update_default_states(
		depot_ids: list[str],
		config_ids: list[str] | None,
		default_states: dict[str, dict[str, dict[str, Any]]],
	) -> dict[str, dict[str, dict[str, Any]]]:
		depot_config_state_objects = service_connection.configState_getObjects(  # type: ignore[attr-defined]
			objectId=depot_ids, configId=config_ids or []
		)
		for state in depot_config_state_objects:
			if state.objectId in default_states and state.configId in default_states[state.objectId]:
				target = default_states[state.object_id][state.configId]
				target["depot_values"] = state.values
				target["origin"] = "depot"
				if target["default_values"] != state.values:
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
				target["client_values"] = state.values
				target["origin"] = "client"
				if target["default_values"] != state:
					target["values"] = state.values

		return depot_states

	service_connection = get_service_connection()
	filter = process_where(where, attributes=COMMAND_METADATA["datastore_config-state_list"].attributes, operation="update")
	config_ids = filter["configId"]
	object_ids = filter["objectId"]

	try:
		final_object_ids = get_validated_object_ids(service_connection, object_ids)
	except ValueError:
		raise

	final_config_ids = [] if config_ids == "*" else get_separated_entries(config_ids)
	config_obj = service_connection.config_getObjects(id=final_config_ids)  # type: ignore[attr-defined]

	if not config_obj:
		raise ValueError(f"There is no such configId: `{config_ids}`")

	# get depot_ids from map
	client_depot_map = create_client_depot_mapping(service_connection, final_object_ids)
	final_depot_ids = list({depot for depot in client_depot_map.values()})

	# remove depot_ids from final_object_ids if no object_ids were given (e.g. object_ids contains all object_ids and depot_ids)
	if object_ids == "*":
		final_object_ids = [id for id in final_object_ids if id not in final_depot_ids]

	default_states = _get_default_config_states(final_object_ids, final_config_ids)
	depot_states = _update_default_states(final_depot_ids, final_object_ids, default_states)
	client_states = _update_depot_states(final_object_ids, final_config_ids, depot_states)

	flattened_result = [state_dict for client_configs in client_states.values() for state_dict in client_configs.values()]
	filtered_data = filter_by_attributes(
		data=flattened_result, attributes=COMMAND_METADATA["datastore_config-state_list"].attributes, filter=filter
	)

	write_output(
		data=filtered_data,
		metadata=COMMAND_METADATA.get("datastore_config-state_list"),
		value_styles={"depot": "yellow", "client": "blue"},
	)


@config_state.command(
	name="update",
	short_help="Update an existing config state or create a new one if it doesn't exist. Using 'all' as the object ID will apply the value to all objects.",
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
					"possible": config_obj.possibleValues,
					"old": current_values[state.objectId][state.configId],
					"new": state.values,
				}
			)
		return sorted(updated_data, key=lambda x: x["objectId"])

	def _update_database(data: list[dict[str, str]], config_states: list[ConfigState], current_values: dict[str, dict[str, str]]) -> None:
		service_connection = get_service_connection()
		update = []
		create = []
		if config.dry_run:
			msg = "Update skipped due to dry run. Here are the clients that would have been updated:\n"
		else:
			msg = "Config-state updated successfully. Here are the updated clients."
			for state in config_states:
				if current_values.get(state.objectId, {}).get(state.configId):
					update.append(state)
				else:
					create.append(state)
			service_connection.configState_updateObjects(update)  # type: ignore[attr-defined]
			service_connection.configState_createObjects(create)  # type: ignore[attr-defined]

		console_print(msg, style="green", output_type=OutputType.MESSAGE)
		write_output(data=data, metadata=COMMAND_METADATA.get("datastore_config-state_update"))

	def _create_config_states(object_ids: list[str], config_id: str, values: list[str] | list[bool]) -> list[ConfigState]:
		config_states = []

		for obj_id in object_ids:
			config_state = ConfigState(configId=config_id, objectId=obj_id, values=values)
			config_states.append(config_state)
		return config_states

	service_connection = get_service_connection()
	filter = process_where(where, attributes=CONFIG_STATE_WHERE_METADATA.attributes, operation="update")

	object_id = filter["objectId"]
	config_id = filter["configId"]

	try:
		object_ids = get_validated_object_ids(service_connection, object_id)
	except ValueError:
		raise

	config_obj = service_connection.config_getObjects(id=config_id)  # type: ignore[attr-defined]

	if not config_obj:
		raise ValueError(f"There is no such configId: `{config_id}`")
	if len(config_obj) > 1:
		raise ValueError("Only one configId without wildcard is allowed.")

	updates = process_set(set, attributes=CONFIG_STATE_SET_METADATA.attributes)
	values = validate_against_possible_values(updates["values"], config_obj[0])
	current_values = service_connection.configState_getValues(config_id, object_ids)  # type: ignore[attr-defined]

	new_config_states = _create_config_states(object_ids, config_obj[0].id, values)
	output_data = _create_output_data(config_obj[0], new_config_states, current_values)
	_update_database(output_data, new_config_states, current_values)
