# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

config-states subcommand
"""

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
from typing import cast

import rich_click as click
from opsicommon.exceptions import BackendMissingDataError
from opsicommon.logging import get_logger
from opsicommon.objects import BoolConfig, ConfigState, ProductOnClient, UnicodeConfig
from opsicommon.types import (
	forceActionRequest,
	forceBool,
	forceHardwareAddress,
	forceInstallationStatus,
	forceIpAddress,
	forceOpsiHostKey,
	forceOpsiTimestamp,
	forceUUIDString,
)

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.config import config
from opsicli.decorators import dry_run_capable
from opsicli.io import OutputType, console_print, get_editor, get_selected_attributes, read_input, write_output
from opsicli.opsiservice import ServiceClient, get_service_connection
from opsicli.plugin import OPSICLIPlugin
from opsicli.types import EditFormat, OutputFormat

from .metadata import command_metadata

__version__ = "0.1.0"
__description__ = "This command can be used to manage data and objects"


logger = get_logger("opsicli")


# handle comma separated object-ids
def get_object_ids(
	service_connection: ServiceClient,
	object_ids: str,
	type: str = "OpsiClient",
) -> list[str]:
	object_id_list = [item.strip() for item in object_ids.split(",")]
	if "all" in object_id_list:
		host_objects = service_connection.host_getObjects(id=[], type=type)  # type: ignore[attr-defined]
		return [obj.id for obj in host_objects]
	return service_connection.host_getIdents(id=object_id_list)  # type: ignore[attr-defined]


def create_client_depot_mapping(service_connection: ServiceClient, object_ids: list[str] | None = None) -> dict[str, str]:
	client_to_depot_objects = service_connection.configState_getClientToDepotserver(clientIds=object_ids or [])  # type: ignore[attr-defined]
	# getClientToDepotserver returns [] for a depot_id
	return {item["clientId"]: item["depotId"] for item in client_to_depot_objects}


def get_depot_to_clients(service_connection: ServiceClient, client_ids: list[str] | None = None) -> dict[str, list[str]]:
	client_to_depot_objects = service_connection.configState_getClientToDepotserver(clientIds=client_ids or [])  # type: ignore[attr-defined]
	depot_to_clients: dict[str, list[str]] = {}
	for item in client_to_depot_objects:
		depot_id = item["depotId"]
		client_id = item["clientId"]
		if depot_id not in depot_to_clients:
			depot_to_clients[depot_id] = []
		depot_to_clients[depot_id].append(client_id)
	return depot_to_clients


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


@cli.group(name="product-client-state", short_help="Product states on clients.")
def product_client_state() -> None:
	"""
	View and change product states on clients.
	"""
	pass


@dataclass
class ProductClientState:
	productType: str
	productId: str
	clientId: str
	installationStatus: str = "not_installed"
	actionRequest: str = "none"
	productVersion: str | None = None
	packageVersion: str | None = None
	modificationTime: datetime | None = None


PRODUCT_CLIENT_STATE_VALUE_STYLES = {
	"installed": "green",
	"unknown": "yellow",
	"setup": "yellow",
	"uninstall": "yellow",
	"update": "yellow",
	"always": "yellow",
	"once": "yellow",
	"custom": "yellow",
}


@product_client_state.command(name="list", short_help="List client product states.")
@click.option(
	"--client-ids",
	type=str,
	required=True,
	help="Filter by client ID(s). Use commas as separators and 'all' to include all IDs. Wildcards (*) are supported.",
)
@click.option(
	"--product-ids",
	type=str,
	required=True,
	help="Filter by product ID(s). Use commas as separators and 'all' to include all IDs. Wildcards (*) are supported.",
)
@click.option(
	"--installation-statuses",
	type=str,
	default="all",
	help=(
		"Filter by installation statuses. Use commas as separators and 'all' to include all statuses. "
		"Possible values are: 'installed', 'not_installed', 'unknown', 'all'."
	),
)
@click.option(
	"--action-requests",
	type=str,
	default="all",
	help=(
		"Filter by action requests. Use commas as separators and 'all' to include all action requests. "
		"Possible values are: 'setup', 'uninstall', 'update', 'always', 'once', 'custom', 'none', 'all'."
	),
)
def list_product_client_state(client_ids: str, product_ids: str, installation_statuses: str, action_requests: str) -> None:
	"""
	View product states on clients.
	"""
	service_connection = get_service_connection()
	filter_client_ids = get_object_ids(service_connection, client_ids)
	filter_product_ids = None if product_ids == "all" else [item.strip() for item in product_ids.split(",")]

	tmp_list = [item.strip() for item in installation_statuses.split(",")]
	filter_installation_statuses = (
		["installed", "not_installed", "unknown"] if "all" in tmp_list else [forceInstallationStatus(item) for item in tmp_list]
	)

	tmp_list = [item.strip() for item in action_requests.split(",")]
	filter_action_requests = (
		["setup", "uninstall", "update", "always", "once", "custom", "none"]
		if "all" in tmp_list
		else [forceActionRequest(item) for item in tmp_list]
	)

	product_states: dict[str, ProductClientState] = {}
	if "none" in filter_action_requests and "not_installed" in filter_installation_statuses:
		depot_to_clients = get_depot_to_clients(service_connection, filter_client_ids)
		depot_ids = list(depot_to_clients)
		for pod in service_connection.productOnDepot_getIdents(returnType="dict", productId=filter_product_ids, depotId=depot_ids):  # type: ignore[attr-defined]
			for client_id in depot_to_clients.get(pod["depotId"], []):
				product_states[f"{client_id};{pod['productId']}"] = ProductClientState(
					productType=pod["productType"],
					productId=pod["productId"],
					clientId=client_id,
					installationStatus="not_installed",
					actionRequest="none",
				)

	for poc in service_connection.productOnClient_getObjects(  # type: ignore[attr-defined]
		clientId=filter_client_ids,
		productId=filter_product_ids or [],
		installationStatus=filter_installation_statuses,
		actionRequest=filter_action_requests,
	):
		poc = cast(ProductOnClient, poc)
		product_states[f"{poc.clientId};{poc.productId}"] = ProductClientState(
			productType=poc.productType,
			productId=poc.productId,
			clientId=poc.clientId,
			installationStatus=poc.installationStatus or "not_installed",
			actionRequest=poc.actionRequest or "none",
			productVersion=poc.productVersion,
			packageVersion=poc.packageVersion,
			modificationTime=datetime.fromisoformat(f"{poc.modificationTime}Z") if poc.modificationTime else None,
		)

	write_output(
		data=list(product_states.values()),
		metadata=command_metadata.get("datastore_product-client-state_list"),
		value_styles=PRODUCT_CLIENT_STATE_VALUE_STYLES,
	)


@product_client_state.command(name="update", short_help="Update client product states.")
@dry_run_capable
def update_product_client_state() -> None:
	"""
	Update product states on clients.
	"""
	data = read_input()
	if not data:
		raise ValueError("No input data provided for updating product client states.")

	pcs = []
	modification_time = datetime.now(tz=timezone.utc).replace(microsecond=0)
	for product_state in data:
		pcs.append(
			ProductClientState(
				clientId=product_state["clientId"],
				productId=product_state["productId"],
				productType=product_state.get("productType"),
				productVersion=product_state.get("productVersion") or None,
				packageVersion=product_state.get("packageVersion") or None,
				installationStatus=forceInstallationStatus(product_state.get("installationStatus") or "not_installed"),
				actionRequest=forceActionRequest(product_state.get("actionRequest") or "none") or "none",
				modificationTime=modification_time,
			)
		)

	if config.dry_run:
		msg = "Update skipped due to dry run. Here are the product client states that would have been updated:\n"
	else:
		service_connection = get_service_connection()
		service_connection.productOnClient_updateObjects(pcs)  # type: ignore[attr-defined]
		msg = "Product client states updated successfully. Here are the updated states:\n"

	console_print(msg, style="green", output_type=OutputType.MESSAGE)
	write_output(
		data=pcs,
		metadata=command_metadata["datastore_product-client-state_list"],
		value_styles=PRODUCT_CLIENT_STATE_VALUE_STYLES,
	)


def _get_clients_from_input() -> list[dict[str, str | datetime | None]]:
	data = read_input()
	if not data:
		return []

	clients = []
	for client in data:
		client["type"] = "OpsiClient"
		for time_field in ["created", "lastSeen"]:
			if value := client.get(time_field):
				client[time_field] = datetime.fromisoformat(value).astimezone(timezone.utc).replace(microsecond=0)
		clients.append(client)
	return clients


def _update_clients(clients: list[dict[str, str | datetime | None]]) -> None:
	if config.dry_run:
		msg = "Update skipped due to dry run. Here are the clients that would have been updated:\n"
	else:
		service_connection = get_service_connection()
		service_connection.host_updateObjects(clients)  # type: ignore[attr-defined]
		msg = "Clients updated successfully. Here are the updated clients:\n"

	console_print(msg, style="green", output_type=OutputType.MESSAGE)
	write_output(data=clients, metadata=command_metadata.get("datastore_client_list"))


def _get_clients_from_service(client_ids: str) -> list[dict[str, str | datetime | None]]:
	selected_attributes = get_selected_attributes(metadata=command_metadata.get("datastore_client_list"))
	if "id" not in selected_attributes:
		selected_attributes.insert(0, "id")

	filter_client_ids = [item.strip() for item in client_ids.split(",")]
	if "all" in filter_client_ids:
		filter_client_ids = []
	else:
		filter_client_ids = [item.strip() for item in filter_client_ids]

	service_connection = get_service_connection()
	clients = []
	for client in service_connection.host_getObjects(attributes=selected_attributes, type="OpsiClient", id=filter_client_ids):  # type: ignore[attr-defined]
		client_hash = {attr: val for attr, val in client.to_hash().items() if attr == "type" or attr in selected_attributes}
		for time_field in ["created", "lastSeen"]:
			if val := client_hash.get(time_field):
				client_hash[time_field] = datetime.fromisoformat(f"{val}Z")
		clients.append(client_hash)
	return clients


@cli.group(name="client", short_help="OPSI client related commands.")
def client() -> None:
	"""
	View and change clients
	"""
	pass


@client.command(name="list", short_help="List clients.")
@click.option(
	"--client-ids",
	type=str,
	default="all",
	help="Filter by client ID(s). Use commas as separators and 'all' to include all IDs. Wildcards (*) are supported.",
)
def list_clients(client_ids: str) -> None:
	"""
	View clients.
	"""
	write_output(data=_get_clients_from_service(client_ids), metadata=command_metadata.get("datastore_client_list"))


@client.command(name="update", short_help="Update clients.")
@dry_run_capable
def update_clients() -> None:
	"""
	Update clients.
	"""
	clients = _get_clients_from_input()
	if not clients:
		raise ValueError("No input data provided for updating clients. Please set --input-file.")

	_update_clients(clients)


@client.command(name="edit", short_help="Edit clients.")
@click.option(
	"--client-ids",
	type=str,
	default="all",
	help="Filter by client ID(s). Use commas as separators and 'all' to include all IDs. Wildcards (*) are supported.",
)
@dry_run_capable
def edit_clients(client_ids: str) -> None:
	"""
	Edit clients.
	"""
	if not config.interactive:
		raise ValueError("Editing is not possible in non-interactive mode.")

	clients = _get_clients_from_service(client_ids)
	edit_format = EditFormat.PRETTY_JSON if config.edit_format == EditFormat.AUTO else config.edit_format

	with NamedTemporaryFile(mode="w", encoding="utf-8", suffix=f".{edit_format.file_extension}") as edit_file:
		orig_output_file = config.output_file
		config.input_file = config.output_file = edit_file.name

		write_output(data=clients, metadata=command_metadata.get("datastore_client_list"), default_output_format=OutputFormat(edit_format))

		cmd = get_editor() + [str(edit_file.name)]
		logger.notice("Opening file '%s' with command: %s", edit_file.name, cmd)
		subprocess.run(cmd)

		edited_clients = _get_clients_from_input()
		changed_clients = [client for client in edited_clients if client not in clients]
		logger.notice("Detected %d changed clients.", len(changed_clients))
		if not changed_clients:
			console_print("No changes detected, no clients were updated.", output_type=OutputType.MESSAGE)
			return

		config.output_file = orig_output_file
		_update_clients(changed_clients)


@client.command(name="set", short_help="Set client attributes.")
@click.argument("client-ids", type=str)
@click.option("--opsiHostKey", type=str, help="Set opsiHostKey to new value.")
@click.option("--description", type=str, help="Set description to new value.")
@click.option("--notes", type=str, help="Set notes to new value.")
@click.option("--hardwareAddress", type=str, help="Set hardwareAddress to new value.")
@click.option("--ipAddress", type=str, help="Set ipAddress to new value.")
@click.option("--inventoryNumber", type=str, help="Set inventoryNumber to new value.")
@click.option("--oneTimePassword", type=str, help="Set oneTimePassword to new value.")
@click.option("--created", type=str, help="Set created to new value. Use ISO format: YYYY-MM-DDTHH:MM:SSZ")
@click.option("--lastSeen", type=str, help="Set lastSeen to new value. Use ISO format: YYYY-MM-DDTHH:MM:SSZ")
@click.option("--systemUUID", type=str, help="Set systemUUID to new value.")
@dry_run_capable
def set_clients(
	client_ids: str,
	opsihostkey: str | None = None,
	description: str | None = None,
	notes: str | None = None,
	hardwareaddress: str | None = None,
	ipaddress: str | None = None,
	inventorynumber: str | None = None,
	onetimepassword: str | None = None,
	created: str | None = None,
	lastseen: str | None = None,
	systemuuid: str | None = None,
) -> None:
	"""
	Set attributes for clients.
	Only the attributes specified as options will be updated, all other attributes will remain unchanged.
	Use --client-ids to specify the target clients by their IDs.
	You can provide multiple client IDs as a comma-separated list or use 'all' to target all clients.
	Wildcards (*) are supported.
	"""

	attributes = []
	if opsihostkey is not None:
		attributes.append("opsiHostKey")
	if description is not None:
		attributes.append("description")
	if notes is not None:
		attributes.append("notes")
	if hardwareaddress is not None:
		attributes.append("hardwareAddress")
	if ipaddress is not None:
		attributes.append("ipAddress")
	if inventorynumber is not None:
		attributes.append("inventoryNumber")
	if onetimepassword is not None:
		attributes.append("oneTimePassword")
	if created is not None:
		attributes.append("created")
	if lastseen is not None:
		attributes.append("lastSeen")
	if systemuuid is not None:
		attributes.append("systemUUID")

	if not attributes:
		raise ValueError("No attributes specified for update. Please provide at least one attribute to set.")

	if not config.attributes:
		config.attributes = ["id"] + attributes

	clients = _get_clients_from_service(client_ids)
	for client in clients:
		if opsihostkey is not None:
			client["opsiHostKey"] = forceOpsiHostKey(opsihostkey)
		if description is not None:
			client["description"] = description
		if notes is not None:
			client["notes"] = notes
		if hardwareaddress is not None:
			client["hardwareAddress"] = forceHardwareAddress(hardwareaddress)
		if ipaddress is not None:
			client["ipAddress"] = forceIpAddress(ipaddress)
		if inventorynumber is not None:
			client["inventoryNumber"] = inventorynumber
		if onetimepassword is not None:
			client["oneTimePassword"] = onetimepassword
		if created is not None:
			client["created"] = forceOpsiTimestamp(datetime.fromisoformat(created).astimezone(timezone.utc).replace(microsecond=0))
		if lastseen is not None:
			client["lastSeen"] = forceOpsiTimestamp(datetime.fromisoformat(lastseen).astimezone(timezone.utc).replace(microsecond=0))
		if systemuuid is not None:
			client["systemUUID"] = forceUUIDString(systemuuid)

	_update_clients(clients)


class DatastorePlugin(OPSICLIPlugin):
	name: str = "Datastore"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
