# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from typing import Any

import rich_click as click
from opsi.logging import get_logger

from opsicli.decorators import mutually_exclusive
from opsicli.io import get_separated_entries, write_output
from opsicli.opsiservice import ServiceClient, get_service_connection

from .common import cli, create_client_depot_mapping, filter_by_attribute_values, get_msg, process_where
from .metadata import COMMAND_METADATA

logger = get_logger("opsicli")


def _get_default_property_states(
	service_connection: ServiceClient, object_ids: list[str], product_ids: list[str], property_ids: list[str], filter: dict[str, str]
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
	bool_attr = [filter.pop("multiValue", None), filter.pop("editable", None)]
	normalized_bool_attr = [
		True if value in ("True", "true", "1") else False if value in ("False", "false", "0") else None for value in bool_attr
	]

	default_property_objects = service_connection.productProperty_getObjects(  # ty: ignore[unresolved-attribute]
		productId=product_ids,
		productVersion=filter.pop("productVersion", None),
		packageVersion=filter.pop("packageVersion", None),
		propertyId=property_ids,
		type=filter.pop("type", None),
		description=filter.pop("description", None),
		editable=normalized_bool_attr[1],
		multiValue=normalized_bool_attr[0],
		value=filter.pop("values", None),
		isDefault=filter.pop("isDefault", None),
	)

	default_states = {}
	for object_id in object_ids:
		default_states[object_id] = {}
		for entry in default_property_objects:
			if entry.productId not in default_states[object_id]:
				default_states[object_id][entry.productId] = {}

			default_states[object_id][entry.productId][entry.propertyId] = {
				"productId": entry.productId,
				"productVersion": entry.productVersion,
				"packageVersion": entry.packageVersion,
				"propertyId": entry.propertyId,
				"description": entry.description,
				"editable": entry.editable,
				"multiValue": entry.multiValue,
				"values": entry.defaultValues,
				"defaultValues": entry.defaultValues,
				"depotValues": "",
				"clientValues": "",
				"origin": "default",
				"objectId": object_id,
			}
	return default_states


def _update_default_states(
	service_connection: ServiceClient,
	client_to_depot: dict[str, str],
	depot_ids: list[str],
	product_ids: list[str],
	property_ids: list[str],
	default_states: dict[str, dict[str, dict[str, dict[str, Any]]]],
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:

	depot_property_states = service_connection.productPropertyState_getObjects(  # ty: ignore[unresolved-attribute]
		objectId=depot_ids, productId=product_ids, propertyId=property_ids
	)

	# account for different depots
	depot_lookup = {(s.objectId, s.productId, s.propertyId): s.values for s in depot_property_states}

	# key: objectId
	for object_id, product_id_dict in default_states.items():
		assigned_depot_id = client_to_depot.get(object_id)
		if not assigned_depot_id:
			continue
		# key: productId
		for product_id, property_id_dict in product_id_dict.items():
			# key: propertyId
			for property_id, default_state in property_id_dict.items():
				if (assigned_depot_id, product_id, property_id) in depot_lookup:
					depot_values = depot_lookup[(assigned_depot_id, product_id, property_id)]
					default_state["depotValues"] = depot_values
					default_state["origin"] = "depot"
					if default_state["defaultValues"] != depot_values:
						default_state["values"] = depot_values

	return default_states


def _update_depot_states(
	service_connection: ServiceClient,
	object_ids: list[str],
	product_ids: list[str],
	property_ids: list[str],
	depot_states: dict[str, dict[str, dict[str, dict[str, Any]]]],
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:

	client_property_states = service_connection.productPropertyState_getObjects(  # ty: ignore[unresolved-attribute]
		objectId=object_ids, productId=product_ids, propertyId=property_ids
	)

	for state in client_property_states:
		for object_id in object_ids:
			if (
				object_id in depot_states
				and state.productId in depot_states[object_id]
				and state.propertyId in depot_states[object_id][state.productId]
			):
				target = depot_states[object_id][state.productId][state.propertyId]
				target["depotValues"] = state.values
				target["origin"] = "depot"
				if target["defaultValues"] != state.values:
					target["values"] = state.values

	return depot_states


@cli.group(name="product-property-state", short_help="Manage properties assigned to software products.")
def product_property_state() -> None:
	"""
	View custom software package configurations (like silent install flags, custom configuration URLs, or serial keys).
	"""
	pass


@product_property_state.command(name="list", short_help="List customized product property values assigned to clients or depots.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter by specific software packages, properties, or host names (e.g., --where 'productId=firefox' --where 'propertyId=disable_telemetry').",
)
@click.option(
	"--all",
	is_flag=True,
	help="Show all software product property assignments, skipping filters completely.",
)
@mutually_exclusive("where", "all")
def list_product_property_state(where: tuple[str, ...], all: bool) -> None:
	"""
	Display custom properties assigned to software products.

	The output resolves OPSI's product property inheritance layer, showing if a state is coming from:
	- The package's default value configuration
	- A depot-server wide adjustment
	- An explicit client-specific installation parameter override
	"""

	service_connection = get_service_connection()
	metadata = COMMAND_METADATA["datastore_product-property-state_list"]
	attributes = metadata.attributes

	if not all:
		filter = process_where(where, attributes=attributes, operation="list")
		filter = {k: (v if v != "*" else "") for k, v in filter.items()}  # process wildcards
	else:
		filter = {}

	# get separated Id's from filter
	final_object_ids = service_connection.host_getIdents(id=get_separated_entries(filter.pop("objectId", None)))  # type: ignore[unresolved-attribute]
	final_product_ids = get_separated_entries(filter.pop("productId", None))
	final_property_ids = get_separated_entries(filter.pop("propertyId", None))
	final_depot_ids = service_connection.host_getIdents(type="OpsiDepotServer")  # type: ignore[unresolved-attribute]

	# map clients to depots
	client_to_depot = create_client_depot_mapping(service_connection, final_object_ids)

	# get default states and update them
	default_states = _get_default_property_states(service_connection, final_object_ids, final_product_ids, final_property_ids, filter)
	depot_states = _update_default_states(
		service_connection, client_to_depot, final_depot_ids, final_product_ids, final_property_ids, default_states
	)
	client_states = _update_depot_states(service_connection, final_object_ids, final_product_ids, final_property_ids, depot_states)

	# prepare data for writing output
	flattened_list: list[dict[str, Any]] = [
		product_property_state
		for product_map in client_states.values()  # objects
		for property_map in product_map.values()  # products
		for product_property_state in property_map.values()  # properties
	]

	result = filter_by_attribute_values(flattened_list, filter, attributes)
	if not result:
		raise ValueError(get_msg("product property states", "no_match"))

	write_output(
		data=sorted(result, key=lambda x: x["objectId"]),
		metadata=metadata,
		value_styles={"depot": "yellow", "client": "blue"},
	)
