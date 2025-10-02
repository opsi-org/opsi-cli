# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

config-states subcommand
"""

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.objects import BoolConfig, OpsiClient, UnicodeConfig

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.decorators import dry_run_handling
from opsicli.io import Attribute, Metadata, write_output
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


@config_state.command(name="list", short_help="List all config states or get a filtered list")
@click.option("--object-id", type=str, default=None, help="Filter data with object_id(s). Use ',' as a separator.")
@click.option("--config-id", type=str, default=None, help="Filter data with config_id. Wildcard * is possible")
def list_config_state(config_id: str | None = None, object_id: str | None = None) -> None:
	"""
	opsi-cli datastore config-state list subcommand.
	"""

	# get depot name/id for given object-id
	def get_depot_id(object_id: str) -> str:
		client_objects = service_connection.configState_getClientToDepotserver()
		for client in client_objects:
			if client["clientId"] == object_id:
				return client["depotId"]

	def get_default_entries(config_id: str) -> dict:
		default_entry_dict = {}
		default_objects = service_connection.config_getObjects(id=config_id or [])
		for entry in default_objects:
			default_entry_dict[entry.id] = [entry.defaultValues, "default"]
		return default_entry_dict

	def get_depot_entries(config_id: str, depot_id: str) -> dict:
		depot_entry_dict = {}
		depot_objects = service_connection.configState_getObjects(configId=config_id or [], objectId=depot_id)
		for entry in depot_objects:
			depot_entry_dict[entry.configId] = [entry.values, "[yellow]server[/yellow]"]
		return depot_entry_dict

	def get_client_entries(config_id: str, object_id: str) -> dict:
		client_entry_dict = {}
		client_objects = service_connection.configState_getObjects(configId=config_id or [], objectId=object_id)
		for entry in client_objects:
			client_entry_dict[entry.configId] = [entry.values, "[red]client[/red]"]
		return client_entry_dict

	def get_all_client_ids() -> list[str]:
		ids = []
		clients = service_connection.host_getObjects()
		for c in clients:
			if isinstance(c, OpsiClient):
				id = c.id
				ids.append(id)
		return ids

	service_connection = get_service_connection()
	# get all objects if no object-id given, otherwise split the object-string
	if object_id is None:
		object_ids = get_all_client_ids()
	else:
		object_ids = object_id.split(",")
		object_ids = [item.strip() for item in object_ids]

	# For every client: create dicts for (default/depot/client) and update them. Print the result
	for obj_id in object_ids:
		result_list = []
		depot_id = get_depot_id(obj_id)
		default_entry_dict = get_default_entries(config_id)
		depot_entry_dict = get_depot_entries(config_id, depot_id)
		client_entry_dict = get_client_entries(config_id, obj_id)

		default_entry_dict.update(depot_entry_dict)
		default_entry_dict.update(client_entry_dict)

		for key, values in default_entry_dict.items():
			temp_list = [key]
			temp_list.extend(values)
			result_list.append(temp_list)
		print(f"\033[1mObjectId:	\033[0m {obj_id}\n\033[1mDepotId:	\033[0m {depot_id}\n\033[1mFilter:		\033[0m {config_id}")
		write_output(result_list, Metadata(attributes=[Attribute(id="configId"), Attribute(id="values"), Attribute(id="origin")]))


class DatastorePlugin(OPSICLIPlugin):
	name: str = "Datastore"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
