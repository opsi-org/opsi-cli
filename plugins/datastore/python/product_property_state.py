# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import rich_click as click
from opsicommon.logging import get_logger

from opsicli.io import write_output
from opsicli.opsiservice import get_service_connection

from .common import cli, create_client_depot_mapping, get_validated_ids
from .metadata import COMMAND_METADATA

logger = get_logger("opsicli")


@cli.group(name="product-property-state", short_help="Configure product property states.")
def product_property_state() -> None:
	"""
	View and manage product property states.
	"""
	pass


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
	final_object_ids = get_validated_ids(service_connection, ids=object_ids, type="objectId")
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
		metadata=COMMAND_METADATA.get("datastore_product-property-state_list"),
		value_styles={"depot": "yellow", "client": "blue"},
	)
