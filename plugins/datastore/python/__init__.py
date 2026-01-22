# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

config-states subcommand
"""

import rich_click as click
from opsicommon.exceptions import BackendMissingDataError
from opsicommon.logging import get_logger
from opsicommon.objects import BoolConfig, ConfigState, UnicodeConfig
from opsicommon.types import forceBool

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.decorators import dry_run_capable
from opsicli.io import OutputType, console_print, write_output
from opsicli.opsiservice import ServiceClient, get_service_connection
from opsicli.plugin import OPSICLIPlugin
from plugins.datastore.data.metadata import command_metadata

__version__ = "0.1.0"
__description__ = "This command can be used to manage data and objects"


logger = get_logger("opsicli")


# handle comma separated object-ids
def get_object_ids(
	service_connection: ServiceClient,
	object_ids: str,
) -> list[str]:
	if object_ids == "all":
		host_objects = service_connection.host_getObjects(id=[], type="OpsiClient")  # type: ignore[attr-defined]
		return [obj.id for obj in host_objects]
	else:
		object_id_list = [item.strip() for item in object_ids.split(",")]
		return service_connection.host_getIdents(id=object_id_list)  # type: ignore[attr-defined]


def create_client_depot_mapping(service_connection: ServiceClient, object_ids: list[str]) -> dict[str, str]:
	client_to_depot_objects = service_connection.configState_getClientToDepotserver(clientIds=object_ids)  # type: ignore[attr-defined]
	# getClientToDepotserver returns [] for a depot_id
	if not client_to_depot_objects:
		client_to_depot_objects = service_connection.configState_getClientToDepotserver()  # type: ignore[attr-defined]
	return {item["clientId"]: item["depotId"] for item in client_to_depot_objects}


# =============================================DATASTORE====================================================
@click.group(cls=OPSICLIGroup, name="datastore", short_help="Manage objects and data")
@click.version_option(__version__, message="datastore plugin, version %(version)s")
@click.pass_context
def cli(ctx: click.Context, **kwargs: str | bool | None) -> None:
	logger.trace("datastore command group")


# =============================================CONFIG-STATE==================================================
@cli.group(name="config-state", short_help="Configure config states.")
def config_state() -> None:
	"""
	View and manage config states.
	"""
	pass


# ===========================================CONFIG-STATE LIST================================================
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
		metadata=command_metadata.get("datastore_config-state_list"),
		value_styles={"depot": "yellow", "client": "blue"},
	)


# ========================================================CONFIG-STATE SET========================================================
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


# ================================================PRODUCT-PROPERTY-STATE=====================================================
@cli.group(name="product-property-state", short_help="Configure product property states.")
def product_property_state() -> None:
	"""
	View and manage product property states.
	"""
	pass


# ==============================================PRODUCT-PROPERTY-STATE LIST===================================================
@product_property_state.command(name="list", short_help="List all product property states or apply filters to narrow the results.")
@click.option(
	"--object-ids",
	type=str,
	required=True,
	help="Filter by object ID(s). Use commas as separators and 'all' to include all IDs. Wildcards (*) are supported.",
)
@click.option(
	"--product-ids",
	type=str,
	required=True,
	help="Filter by product ID(s). Use commas as separators and 'all' to include all IDs. Wildcards (*) are supported.",
)
@click.option(
	"--property-ids",
	type=str,
	default="all",
	help="Filter by property ID(s). Use commas as separators and 'all' to include all IDs. Wildcards (*) are supported.",
)
def list_product_property_state(object_ids: str, product_ids: str, property_ids: str) -> None:
	"""
	View all product property states or apply filters to narrow your search.
	"""

	def get_default_property_states(
		object_ids: list[str], product_id: list[str] | None, property_id: list[str] | None
	) -> dict[str, dict[str, str]]:
		default_property_objects = service_connection.productProperty_getObjects(productId=product_id or [], propertyId=property_id or [])  # type: ignore[attr-defined]
		default_states = {}

		for object_id in object_ids:
			for entry in default_property_objects:
				default_states[object_id + entry.productId + entry.propertyId] = {
					"final_values": entry.defaultValues,
					"default_values": entry.defaultValues,
					"depot_values": "",
					"client_values": "",
					"origin": "default",
					"productId": entry.productId,
					"propertyId": entry.propertyId,
					"objectId": object_id,
				}
		return default_states

	def update_default_states(
		depot_ids: list[str],
		object_ids: list[str],
		product_id: list[str] | None,
		property_id: list[str] | None,
		default_states: dict[str, dict[str, str]],
	) -> dict[str, dict[str, str]]:
		depot_property_objects = service_connection.productPropertyState_getObjects(  # type: ignore[attr-defined]
			objectId=depot_ids, productId=product_id or [], propertyId=property_id or []
		)

		for object_id in object_ids:
			for entry in depot_property_objects:
				key = object_id + entry.productId + entry.propertyId
				default_states[key]["depot_values"] = entry.values
				if default_states[key]["default_values"] != entry.values:
					default_states[key]["final_values"] = entry.values
				default_states[key]["origin"] = "depot"

		return default_states

	def update_depot_states(
		object_ids: list[str],
		product_ids: list[str] | None,
		property_ids: list[str] | None,
		depot_states: dict[str, dict[str, str]],
	) -> dict[str, dict[str, str]]:
		client_property_objects = service_connection.productPropertyState_getObjects(  # type: ignore[attr-defined]
			objectId=object_ids, productId=product_ids or [], propertyId=property_ids or []
		)
		for entry in client_property_objects:
			key = entry.objectId + entry.productId + entry.propertyId
			depot_states[key]["client_values"] = entry.values
			if depot_states[key]["depot_values"] != entry.values:
				depot_states[key]["final_values"] = entry.values
			depot_states[key]["origin"] = "client"
		return depot_states

	service_connection = get_service_connection()
	# Handle different object_id input formats (e.g. plain IDs, IDs with '*', or comma-separated strings)
	final_object_ids = get_object_ids(service_connection, object_ids)
	final_product_ids = None if product_ids == "all" else [item.strip() for item in product_ids.split(",")]
	final_property_ids = None if property_ids == "all" else [item.strip() for item in property_ids.split(",")]

	# get depot_ids from map
	client_depot_map = create_client_depot_mapping(service_connection, final_object_ids)
	depot_ids = list({depot for depot in client_depot_map.values()})

	default_states = get_default_property_states(final_object_ids, final_product_ids, final_property_ids)
	depot_states = update_default_states(depot_ids, final_object_ids, final_product_ids, final_property_ids, default_states)
	client_states = update_depot_states(final_object_ids, final_product_ids, final_property_ids, depot_states)

	write_output(
		data=list(client_states.values()),
		metadata=command_metadata.get("datastore_product-property-state_list"),
		value_styles={"depot": "yellow", "client": "blue"},
	)


# ====================================================PRODUCT========================================================
@cli.group(name="product", short_help="Configure products.")
def product() -> None:
	"""
	Configure products.
	"""
	pass


# ================================================PRODUCT UNLOCK=====================================================
@product.command(name="unlock", short_help="Unlock products on depots.")
@click.option(
	"--product-ids",
	type=str,
	default=None,
	help="Specify the product ID(s) to unlock, using a comma-separated list for multiple entries.",
)
@click.option(
	"--depot-ids",
	type=str,
	default=None,
	help="Specify the target depot ID(s) for product unlocking, using a comma-separated list for multiple entries.",
)
def product_unlock(product_ids: str | None = None, depot_ids: str | None = None) -> None:
	"""
	Remove locks from products on specified depots.
	"""

	# Helper function, get products, unlock them, update them
	def unlock_and_update(product_ids: list[str], depot_ids: list[str]) -> None:
		product_on_depots = service_connection.productOnDepot_getObjects(productId=product_ids, depotId=depot_ids or [])  # type: ignore[attr-defined]
		if not product_on_depots:
			logger.error("No such depot(s): %s", depot_ids)
			raise BackendMissingDataError(f"No such depot(s): {depot_ids}")
		for product_on_depot in product_on_depots:
			product_on_depot.locked = False
		service_connection.productOnDepot_updateObjects(product_on_depots)  # type: ignore[attr-defined]

	service_connection = get_service_connection()
	product_ids_list = [p.strip() for p in (product_ids or "").split(",") if p.strip()]
	depot_ids_list = [d.strip() for d in (depot_ids or "").split(",") if d.strip()]
	unlock_and_update(product_ids_list, depot_ids_list)


@product.command(name="purge", short_help="Purge metadata related to uninstalled products.")
@click.option(
	"--product-ids",
	type=str,
	default=None,
	help="Specify the product ID(s) to unlock, using a comma-separated list for multiple entries.",
)
def product_purge(product_ids: str | None = None) -> None:
	"""
	Remove metadata associated with uninstalled products, such as installation status and product property states.

	"""
	product_id_list = [p.strip() for p in (product_ids or "").split(",") if p.strip()]
	get_service_connection().product_purge(id=product_id_list)  # type: ignore[attr-defined]
	console_print("Product metadata purged successfully.", output_type=OutputType.MESSAGE)


class DatastorePlugin(OPSICLIPlugin):
	name: str = "Datastore"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
