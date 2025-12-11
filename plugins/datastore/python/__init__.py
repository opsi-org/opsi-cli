# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

config-states subcommand
"""

from typing import Any, Literal

import rich_click as click
from opsicommon.exceptions import BackendMissingDataError
from opsicommon.logging import get_logger
from opsicommon.objects import BoolConfig, ConfigState, UnicodeConfig
from opsicommon.types import forceBool

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.decorators import dry_run_handling
from opsicli.io import Attribute, Metadata, console_print, write_output
from opsicli.opsiservice import ServiceClient, get_service_connection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"
__description__ = "This command can be used to manage data and objects"


logger = get_logger("opsicli")


# handle comma separated object-ids
def get_object_ids(
	service_connection: ServiceClient,
	object_id: str | None = None,
) -> list[str]:
	object_ids: list[str] = []
	if not object_id:
		object_ids = service_connection.host_getIdents(id=[])  # type: ignore[attr-defined]
	else:
		if "," in object_id:
			object_id_list = [item.strip() for item in object_id.split(",")]
			for obj_id in object_id_list:
				object_ids = object_ids + service_connection.host_getIdents(id=obj_id)  # type: ignore[attr-defined]
		else:
			object_ids = service_connection.host_getIdents(id=object_id)  # type: ignore[attr-defined]
	return object_ids


# get depot name/id for given object-id
def get_depot_id(object_id: str, client_to_server_objects: list[dict[str, Any]]) -> str:
	for client in client_to_server_objects:
		if client["clientId"] == object_id:
			return client["depotId"]
	raise ValueError(f"No depot found for host '{object_id}'.")


# DATASTORE
@click.group(cls=OPSICLIGroup, name="datastore", short_help="Manage data and objects")
@click.version_option(__version__, message="datastore plugin, version %(version)s")
@click.pass_context
@dry_run_handling(dry_run_capable=True)
def cli(ctx: click.Context, **kwargs: str | bool | None) -> None:
	logger.trace("datastore command group")


# CONFIG-STATE
@cli.group(name="config-state", short_help="Change config state(s)")
def config_state() -> None:
	"""
	opsi-cli datastore config-state subcommand.
	"""
	pass


# =======================================CONFIG-STATE LIST===========================================
@config_state.command(name="list", short_help="List all config states or get a filtered list. ")
@click.option("--object-id", type=str, default=None, help="Filter data with object_id(s). Use ',' as a separator. Wildcard * is possible.")
@click.option("--config-id", type=str, default=None, help="Filter data with config_id. Wildcard * is possible.")
def list_config_state(config_id: str | None = None, object_id: str | None = None) -> None:
	"""
	opsi-cli datastore config-state list subcommand.
	"""

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


# =======================================CONFIG-STATE SET=============================================
@config_state.command(
	name="set",
	short_help="Change a config state value. Create a config state if there is none. If 'all' is used as an objectId, the value will be set for all objects.",
)
@click.argument("config-id", type=str)
@click.argument("object-id", type=str)
@click.argument("values", type=str, nargs=-1)
def set_config_state_value(config_id: str, object_id: str | None, values: tuple[str]) -> None:
	"""
	opsi-cli datastore config-state set subcommand.
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

	# get all object_id's if object_id is 'all'
	if object_id == "all":
		host_objects = service_connection.host_getObjects(id=[], type="OpsiClient")  # type: ignore[attr-defined]
		object_ids = [obj.id for obj in host_objects]
	else:
		object_ids = [object_id]

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


# PRODUCT-PROPERTY-STATE
@cli.group(name="product-property-state", short_help="Change product-property-states.")
def product_property_state() -> None:
	"""
	opsi-cli datastore product-property-state subcommand.
	"""
	pass


# ====================================PRODUCT-PROPERTY-STATE LIST=======================================
@product_property_state.command(name="list", short_help="List all product-property-states or get a filtered list. ")
@click.option("--object-id", type=str, default=None, help="Filter data with object_id(s). Use ',' as a separator. Wildcard * is possible.")
@click.option("--product-id", type=str, default=None, help="Filter data with product_id. Wildcard * is possible.")
@click.option("--property-id", type=str, default=None, help="Filter data with property_id. Wildcard * is possible. ")
def list_product_property_state(object_id: str | None = None, product_id: str | None = None, property_id: str | None = None) -> None:
	"""
	opsi-cli datastore product-property-state list subcommand.
	"""

	def get_default_property_states(object_ids: list[str], product_id: str | None, property_id: str | None) -> dict[str, dict[str, str]]:
		default_property_objects = service_connection.productProperty_getObjects(productId=product_id or [], propertyId=property_id or [])  # type: ignore[attr-defined]
		default_states = {}

		for object_id in object_ids:
			for entry in default_property_objects:
				default_states[object_id + entry.productId + entry.propertyId] = {
					"values": entry.defaultValues,
					"origin": "default",
					"productId": entry.productId,
					"propertyId": entry.propertyId,
					"objectId": object_id,
				}
		return default_states

	def update_default_states(
		depot_ids: list[str],
		object_ids: list[str],
		product_id: str | None,
		property_id: str | None,
		default_states: dict[str, dict[str, str]],
	) -> dict[str, dict[str, str]]:
		depot_property_objects = service_connection.productPropertyState_getObjects(  # type: ignore[attr-defined]
			objectId=depot_ids, productId=product_id or [], propertyId=property_id or []
		)
		for object_id in object_ids:
			for entry in depot_property_objects:
				key = object_id + entry.productId + entry.propertyId
				if key in default_states and default_states[key]["values"] != entry.values:
					default_states[key]["values"] = entry.values
					default_states[key]["origin"] = "[yellow]server[/yellow]"

		return default_states

	def update_depot_states(
		object_ids: list[str],
		product_id: str | None,
		property_id: str | None,
		depot_states: dict[str, dict[str, str]],
	) -> dict[str, dict[str, str]]:
		client_property_objects = service_connection.productPropertyState_getObjects(  # type: ignore[attr-defined]
			objectId=object_ids, productId=product_id or [], propertyId=property_id or []
		)
		for entry in client_property_objects:
			key = entry.objectId + entry.productId + entry.propertyId
			if key in depot_states and depot_states[key]["values"] != entry.values:
				depot_states[key]["values"] = entry.values
				depot_states[key]["origin"] = "[blue]client[/blue]"
		return default_states

	service_connection = get_service_connection()

	# handle different object_id input (e.g. normal, with * or comma seperated)
	# getClientToDepotserver does not accept wildcards '*', getIdents in get_object_ids does.
	object_ids = get_object_ids(service_connection, object_id)

	# map objectId's to depotId's for easier access
	# getClientToDepotserver returns [] for a depot_id
	client_to_depot_objects = service_connection.configState_getClientToDepotserver(clientIds=object_ids)  # type: ignore[attr-defined]
	if not client_to_depot_objects:
		client_to_depot_objects = service_connection.configState_getClientToDepotserver()  # type: ignore[attr-defined]
		client_depot_map = {item["clientId"]: item["depotId"] for item in client_to_depot_objects}
	else:
		client_depot_map = {item["clientId"]: item["depotId"] for item in client_to_depot_objects}

	# get depot_ids from map
	depot_ids = list({depot for depot in client_depot_map.values()})

	# remove depot_ids from object_ids if no object_ids were given (e.g. object_ids contains all object_ids and depot_ids)
	if not object_id:
		object_ids = [id for id in object_ids if id not in depot_ids]

	default_states = get_default_property_states(object_ids, product_id, property_id)
	depot_states = update_default_states(depot_ids, object_ids, product_id, property_id, default_states)
	client_states = update_depot_states(object_ids, product_id, property_id, depot_states)

	write_output(
		list(client_states.values()),
		Metadata(
			attributes=[
				Attribute(id="objectId", description="The ID of the object.", identifier=False, data_type="str", selected=True),
				Attribute(id="productId", description="The ID of the product.", identifier=False, data_type="str", selected=True),
				Attribute(id="propertyId", description="The ID of the property.", identifier=False, data_type="str", selected=True),
				Attribute(id="values", description="Values of given property.", identifier=False, data_type="str | Boolean", selected=True),
				Attribute(id="origin", description="Location where the change was made.", identifier=False, data_type="str", selected=True),
			]
		),
	)


# PRODUCT
@cli.group(name="product", short_help="Configure products")
def product() -> None:
	"""
	opsi-cli dawtastore config-state subcommand.
	"""
	pass


# =========================================PRODUCT UNLOCK==============================================
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
