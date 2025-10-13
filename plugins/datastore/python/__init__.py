# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

config-states subcommand
"""

from typing import Literal

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.objects import BoolConfig, ConfigState, UnicodeConfig
from opsicommon.types import forceBool

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.decorators import dry_run_handling
from opsicli.io import Attribute, Metadata, console_print, write_output
from opsicli.opsiservice import get_service_connection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"
__description__ = "This command can be used to manage data and objects"


logger = get_logger("opsicli")


@click.group(cls=OPSICLIGroup, name="datastore", short_help="Manage data and objects")
@click.version_option(__version__, message="datastore plugin, version %(version)s")
@click.pass_context
@dry_run_handling(dry_run_capable=True)
def cli(ctx: click.Context, **kwargs: str | bool | None) -> None:
	logger.trace("datastore command group")


@cli.group(name="config-state", short_help="Change config state(s)")
def config_state() -> None:
	"""
	opsi-cli datastore config-state subcommand.
	"""
	pass


@config_state.command(name="list", short_help="List all config states or get a filtered list. ")
@click.option("--object-id", type=str, default=None, help="Filter data with object_id(s). Use ',' as a separator. Wildcard * is possible.")
@click.option("--config-id", type=str, default=None, help="Filter data with config_id. Wildcard * is possible.")
def list_config_state(config_id: str | None = None, object_id: str | None = None) -> None:
	"""
	opsi-cli datastore config-state list subcommand.
	"""

	# get depot name/id for given object-id
	def get_depot_id(object_id: str, client_to_server_objects: list[dict]) -> str:
		for client in client_to_server_objects:
			if client["clientId"] == object_id:
				return client["depotId"]
		raise ValueError(f"No depot found for host '{object_id}'.")

	def get_default_entries(config_id: str | None, object_id: str, depot_id: str) -> dict[str, dict[str, str]]:
		default_entry_dict = {}
		default_objects = service_connection.config_getObjects(id=config_id or [])  # type: ignore[attr-defined]
		for entry in default_objects:
			default_entry_dict[entry.id] = {
				"values": entry.defaultValues,
				"origin": "default",
				"configId": entry.id,
				"objectId": object_id,
				"depotId": depot_id,
			}
		return default_entry_dict

	def get_host_entries(
		config_id: str | None,
		object_id: str,
		depot_id: str,
		host_type: Literal["OpsiClient", "OpsiDepotserver"],
	) -> dict[str, dict[str, str]]:
		origin = "[yellow]server[/yellow]" if host_type == "OpsiDepotserver" else "[blue]client[/blue]"
		entry_dict = {}
		depot_objects = service_connection.configState_getObjects(  # type: ignore[attr-defined]
			configId=config_id or [], objectId=object_id if host_type == "OpsiClient" else depot_id
		)
		for entry in depot_objects:
			entry_dict[entry.configId] = {
				"values": entry.values,
				"origin": origin,
				"configId": entry.configId,
				"objectId": object_id,
				"depotId": depot_id,
			}
		return entry_dict

	service_connection = get_service_connection()
	client_to_server_objects = service_connection.configState_getClientToDepotserver()  # type: ignore[attr-defined]
	host_objects = []
	config_ids: list[str | None] = []
	result_unique = []
	result = []

	# handle comma separated object-ids
	if not object_id:
		host_objects = service_connection.host_getObjects(id=[], type="OpsiClient")  # type: ignore[attr-defined]
	else:
		if "," in object_id:
			object_ids = [item.strip() for item in object_id.split(",")]
			for obj_id in object_ids:
				host_objects = host_objects + service_connection.host_getObjects(id=obj_id, type="OpsiClient")  # type: ignore[attr-defined]
			host_objects = list(set(host_objects))
		else:
			host_objects = service_connection.host_getObjects(id=object_id, type="OpsiClient")  # type: ignore[attr-defined]

	# handle comma separated config-ids
	if config_id:
		if "," in config_id:
			config_ids = [item.strip() for item in config_id.split(",")]
		else:
			config_ids.append(config_id)
	else:
		config_ids.append(config_id)

	# For every client: create dicts for (default/depot/client) and update them. Print the result
	for obj in host_objects:
		depot_id = get_depot_id(obj.id, client_to_server_objects)

		for conf_id in config_ids:
			default_entry_dict = get_default_entries(conf_id, obj.id, depot_id)
			depot_entry_dict = get_host_entries(conf_id, obj.id, depot_id, "OpsiDepotserver")
			client_entry_dict = get_host_entries(conf_id, obj.id, depot_id, "OpsiClient")

			default_entry_dict.update(depot_entry_dict)
			default_entry_dict.update(client_entry_dict)

			result.extend(list(default_entry_dict.values()))

	# get rid of duplicates
	for entry in result:
		if entry not in result_unique:
			result_unique.append(entry)

	write_output(
		result_unique,
		Metadata(
			attributes=[
				Attribute(id="objectId", description="The ID of the object (host).", identifier=False, data_type="str", selected=True),
				Attribute(
					id="depotId", description="The ID of the object's (host's) depot.", identifier=False, data_type="str", selected=False
				),
				Attribute(id="configId", description="The ID of the config.", identifier=False, data_type="str", selected=True),
				Attribute(id="values", description="Values of given configs.", identifier=False, data_type="str | Boolean", selected=True),
				Attribute(id="origin", description="Location where the change was made.", identifier=False, data_type="str", selected=True),
			]
		),
	)


@config_state.command(name="set", short_help="Changes config state value. Create config state if there is none.")
@click.argument("config-id", type=str)
@click.argument("object-id", type=str)
@click.argument("value", type=str)
def set_config_state_value(config_id: str, object_id: str, value: str) -> None:
	"""
	opsi-cli datastore config-state set subcommand.
	"""
	# get server connection and the config object with given config_id
	service_connection = get_service_connection()
	config_list = service_connection.config_getObjects(id=config_id)  # type: ignore[attr-defined]
	config_state_list = service_connection.configState_getObjects(configId=config_id)  # type: ignore[attr-defined]

	# test if a config for config_id exists
	if not config_list:
		raise AttributeError(f"There is no such configId: '{config_id}'")
	if len(config_list) > 1:
		raise AttributeError("Only one configId without wildcard is allowed.")
	config = config_list[0]
	config_state_exists = config_state_list[0]

	possible_values = config.possibleValues
	host_objects = service_connection.host_getObjects(id=object_id, type="OpsiClient")  # type: ignore[attr-defined]
	object_ids = [obj.id for obj in host_objects]
	object_value_dict = service_connection.configState_getValues(config_id, object_ids)  # type: ignore[attr-defined]

	# set value for every given object
	for obj_id in object_ids:
		current_values = object_value_dict[obj_id][config_id]
		# test if config is type BoolConfig
		if isinstance(config, BoolConfig):
			if value in ["true", "True"]:
				config_state = ConfigState(configId=config_id, objectId=obj_id, values=[forceBool(value)])
			elif value in ["false", "False"]:
				config_state = ConfigState(configId=config_id, objectId=obj_id, values=[forceBool(value)])
			else:
				raise ValueError(f"'{value}' is not a valid value. Possible values are: {possible_values}")
			if config_state_exists:
				service_connection.configState_updateObject(config_state)  # type: ignore[attr-defined]
			else:
				service_connection.configState_createObject(config_state)  # type: ignore[attr-defined]
			console_print(
				f"[yellow]{config_id}[/yellow] changed successfully for [yellow]{obj_id}[/yellow]. \nOld value: [red]{current_values}[/red] \nNew value: [green]{[forceBool(value)]}[/green]\n"
			)

		# test if config is type UnicodeConfig
		if isinstance(config, UnicodeConfig):
			if not config.multiValue:
				if value in possible_values:
					config_state = ConfigState(configId=config_id, objectId=obj_id, values=[value])

					if config_state_exists:
						service_connection.configState_updateObject(config_state)  # type: ignore[attr-defined]
					else:
						service_connection.configState_createObject(config_state)  # type: ignore[attr-defined]

					console_print(
						f"[yellow]{config_id}[/yellow] changed successfully for [yellow]{obj_id}[/yellow]. \nOld value: [red]{current_values}[/red] \nNew value: [green]{[value]}[/green]\n"
					)
				else:
					raise ValueError(
						f"Value is not valid for [yellow]{config_id}[/yellow]. \nPossible values are: [green]{possible_values}[/green]"
					)
			else:
				value_list = [item.strip() for item in value.split(",")].sort()
				config_state = ConfigState(configId=config_id, objectId=obj_id, values=value_list)

				if config_state_exists:
					service_connection.configState_updateObject(config_state)  # type: ignore[attr-defined]
				else:
					service_connection.configState_createObject(config_state)  # type: ignore[attr-defined]

				console_print(
					f"[yellow]{config_id}[/yellow] changed successfully for [yellow]{obj_id}[/yellow]. \nOld value: [red]{current_values}[/red] \nNew values: [green]{value_list}[/green]\n"
				)


class DatastorePlugin(OPSICLIPlugin):
	name: str = "Datastore"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
