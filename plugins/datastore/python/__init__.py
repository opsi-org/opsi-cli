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
from opsicommon.exceptions import BackendMissingDataError
from opsicommon.logging import get_logger

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


@config_state.command(name="list", short_help="List all config states or get a filtered list")
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

	def get_default_entries(config_id: str | list[str], object_id: str, depot_id: str) -> dict[str, dict[str, str]]:
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
		config_id: str | list[str],
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
	host_objects = service_connection.host_getObjects(id=object_id or [], type="OpsiClient")  # type: ignore[attr-defined]
	result = []

	# For every client: create dicts for (default/depot/client) and update them. Print the result
	for obj in host_objects:
		depot_id = get_depot_id(obj.id, client_to_server_objects)

		default_entry_dict = get_default_entries(config_id or [], obj.id, depot_id)
		depot_entry_dict = get_host_entries(config_id or [], obj.id, depot_id, "OpsiDepotserver")
		client_entry_dict = get_host_entries(config_id or [], obj.id, depot_id, "OpsiClient")

		default_entry_dict.update(depot_entry_dict)
		default_entry_dict.update(client_entry_dict)

		result.extend(list(default_entry_dict.values()))

	write_output(
		result,
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


@cli.group(name="product", short_help="Configure products")
def product() -> None:
	"""
	opsi-cli datastore config-state subcommand.
	"""
	pass


@product.command(name="unlock", short_help="Unlock product(s) on depot(s).")
@click.argument("product-id", type=str, nargs=-1)
@click.option("--depot-id", type=str, default=None, help="Choose the depot-id(s) where products should be unlocked. Comma seperated list.")
def unlock_product(product_id: tuple[str], depot_id: str | None = None) -> None:
	# help function, get products, unlock them, update them
	def unlock_and_update(product_id: list[str], depot_id: list[str]) -> None:
		product_on_depots = service_connection.productOnDepot_getObjects(productId=product_id, depotId=depot_id or [])  # type: ignore[attr-defined]
		if not product_on_depots:
			logger.error("No such depot(s): %s", depot_id)
			raise BackendMissingDataError(f"No such depot(s): {depot_id}")
		for product_on_depot in product_on_depots:
			product_on_depot.locked = False
		service_connection.productOnDepot_updateObjects(product_on_depots)  # type: ignore[attr-defined]

	service_connection = get_service_connection()
	product_id_list = list(product_id)

	if depot_id:
		depot_id_list = [item.strip() for item in depot_id.split(",")]
		# unlock products on every given depot
		unlock_and_update(product_id_list, depot_id_list)
	else:
		# unlock products on ALL depots
		unlock_and_update(product_id_list, [])


class DatastorePlugin(OPSICLIPlugin):
	name: str = "Datastore"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
