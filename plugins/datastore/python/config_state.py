# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.objects import BoolConfig, ConfigState, UnicodeConfig
from opsicommon.types import forceBool

from opsicli.io import console_print, write_output
from opsicli.opsiservice import get_service_connection

from .common import cli, create_client_depot_mapping, get_object_ids
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
	"--object-ids",
	type=str,
	required=True,
	help="Filter by object ID(s). Use commas as separators and 'all' to include all IDs. Wildcards (*) are supported.",
)
@click.option(
	"--config-ids",
	type=str,
	required=True,
	help="Filter by config ID(s). Use commas as separators and 'all' to include all IDs. Wildcards (*) are supported.",
)
def list_config_state(object_ids: str, config_ids: str) -> None:
	"""
	View all configuration states or apply filters to narrow your search.
	"""

	def get_default_config_states(object_ids: list[str], config_ids: list[str] | None) -> dict[str, dict[str, str]]:
		default_config_objects = service_connection.config_getObjects(id=config_ids or [])  # type: ignore[attr-defined]
		default_states = {}

		for object_id in object_ids:
			for entry in default_config_objects:
				default_states[object_id + entry.id] = {
					"final_values": entry.defaultValues,
					"default_values": entry.defaultValues,
					"depot_values": "",
					"client_values": "",
					"origin": "default",
					"configId": entry.id,
					"objectId": object_id,
				}
		return default_states

	def update_default_states(
		depot_ids: list[str],
		object_ids: list[str],
		config_ids: list[str] | None,
		default_states: dict[str, dict[str, str]],
	) -> dict[str, dict[str, str]]:
		depot_config_state_objects = service_connection.configState_getObjects(  # type: ignore[attr-defined]
			objectId=depot_ids, configId=config_ids or []
		)
		for object_id in object_ids:
			for entry in depot_config_state_objects:
				key = object_id + entry.configId
				default_states[key]["depot_values"] = entry.values
				default_states[key]["origin"] = "depot"
				if default_states[key]["default_values"] != entry.values:
					default_states[key]["final_values"] = entry.values

		return default_states

	def update_depot_states(
		object_ids: list[str],
		config_ids: list[str] | None,
		depot_states: dict[str, dict[str, str]],
	) -> dict[str, dict[str, str]]:
		client_config_state_objects = service_connection.configState_getObjects(  # type: ignore[attr-defined]
			objectId=object_ids, configId=config_ids or []
		)

		for entry in client_config_state_objects:
			key = entry.objectId + entry.configId
			depot_states[key]["client_values"] = entry.values
			depot_states[key]["origin"] = "client"
			if key in depot_states:
				depot_states[key]["final_values"] = entry.values

		return depot_states

	service_connection = get_service_connection()
	# Handle different input formats (e.g. plain IDs, IDs with '*', or comma-separated strings)
	final_object_ids = get_object_ids(service_connection, object_ids)
	final_config_ids = None if config_ids == "all" else [item.strip() for item in config_ids.split(",")]

	# get depot_ids from map
	client_depot_map = create_client_depot_mapping(service_connection, final_object_ids)
	final_depot_ids = list({depot for depot in client_depot_map.values()})

	# remove depot_ids from final_object_ids if no object_ids were given (e.g. object_ids contains all object_ids and depot_ids)
	if object_ids == "all":
		final_object_ids = [id for id in final_object_ids if id not in final_depot_ids]

	default_states = get_default_config_states(final_object_ids, final_config_ids)
	depot_states = update_default_states(final_depot_ids, final_object_ids, final_config_ids, default_states)
	client_states = update_depot_states(final_object_ids, final_config_ids, depot_states)

	write_output(
		data=list(client_states.values()),
		metadata=COMMAND_METADATA.get("datastore_config-state_list"),
		value_styles={"depot": "yellow", "client": "blue"},
	)


@config_state.command(
	name="set",
	short_help="Update an existing config state or create a new one if it doesn't exist. Using 'all' as the object ID will apply the value to all objects.",
)
@click.argument("config-id", type=str)
@click.argument("object-id", type=str)
@click.argument("values", type=str, nargs=-1)
def set_config_state_value(config_id: str, object_id: str, values: tuple[str]) -> None:
	"""
	Change values of config states.
	"""

	def set_bool_config(object_ids: list[str], config_id: str, value: str) -> None:
		possible_values = config.possibleValues
		object_value_dict = service_connection.configState_getValues(config_id, object_ids)  # type: ignore[attr-defined]
		# set new value for every given object
		for obj_id in object_ids:
			current_values = object_value_dict[obj_id][config_id]
			# create configState Objects with new value
			if value in ["true", "True"]:
				config_state = ConfigState(configId=config_id, objectId=obj_id, values=[forceBool(value)])
			elif value in ["false", "False"]:
				config_state = ConfigState(configId=config_id, objectId=obj_id, values=[forceBool(value)])
			else:
				raise ValueError(f"'{value}' is not valid for {config_id}. Possible values are: {possible_values}")

			# update current configState Objects
			if config_state_exists:
				service_connection.configState_updateObjects(config_state)  # type: ignore[attr-defined]
			else:
				service_connection.configState_createObjects(config_state)  # type: ignore[attr-defined]

			console_print(
				f"[yellow]{config_id}[/yellow] changed successfully for [yellow]{obj_id}[/yellow]. \nOld value: [red]{current_values}[/red] \nNew value: [green]{[forceBool(value[0])]}[/green]\n"
			)

	def set_unicode_config(object_ids: list[str], config_id: str, value: list[str]) -> None:
		possible_values = config.possibleValues
		object_value_dict = service_connection.configState_getValues(config_id, object_ids)  # type: ignore[attr-defined]
		# set new value for every given object
		for obj_id in object_ids:
			current_values = object_value_dict[obj_id][config_id]

			# [one value]
			if len(value) == 1:
				# check for possible values if config is not multiValue
				if value[0] not in possible_values and config.multiValue is False:
					raise ValueError(
						f"Value is not valid for [yellow]{config_id}[/yellow]. \nPossible values are: [green]{possible_values}[/green]"
					)
				# craete configState
				config_state = ConfigState(configId=config_id, objectId=obj_id, values=value)

				# update configState
				if config_state_exists:
					service_connection.configState_updateObjects(config_state)  # type: ignore[attr-defined]
				else:
					service_connection.configState_createObjects(config_state)  # type: ignore[attr-defined]

				console_print(
					f"[yellow]{config_id}[/yellow] changed successfully for [yellow]{obj_id}[/yellow]. \nOld value: [red]{current_values}[/red] \nNew value: [green]{value}[/green]\n"
				)
			# [multiple values or no value]
			else:
				if not config.multiValue:
					raise ValueError(f"Value is not valid for [yellow]{config_id}[/yellow]. \nMultivalues are not allowed.")
				# create configState
				config_state = ConfigState(configId=config_id, objectId=obj_id, values=value)

				# update configState
				if config_state_exists:
					service_connection.configState_updateObjects(config_state)  # type: ignore[attr-defined]
				else:
					service_connection.configState_createObjects(config_state)  # type: ignore[attr-defined]

				console_print(
					f"[yellow]{config_id}[/yellow] changed successfully for [yellow]{obj_id}[/yellow]. \nOld value: [red]{current_values}[/red] \nNew value: [green]{value}[/green]\n"
				)

	# get server connection and the config object with given config_id
	service_connection = get_service_connection()
	config_list = service_connection.config_getObjects(id=config_id)  # type: ignore[attr-defined]
	config_state_list = service_connection.configState_getObjects(configId=config_id)  # type: ignore[attr-defined]

	# test if config-id is valid
	if not config_list:
		raise AttributeError(f"There is no such configId: '{config_id}'")
	if len(config_list) > 1:
		raise AttributeError("Only one configId without wildcard is allowed.")

	# get config from list
	config = config_list[0]
	config_state_exists = False if config_state_list == [] else True

	possible_values = config.possibleValues

	object_ids = get_object_ids(service_connection, object_id)

	# set BoolConfig
	if isinstance(config, BoolConfig):
		if len(values) == 1:
			set_bool_config(object_ids, config_id, values[0])
		else:
			raise ValueError(
				f"Multivalues are not valid for [yellow]{config_id}[/yellow] \nPossible values are: [green]{possible_values}[/green]"
			)
	# set UnicodeConfig
	if isinstance(config, UnicodeConfig):
		set_unicode_config(object_ids, config_id, list(values))
