# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only
from typing import Any

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.types import forceBool

from opsicli.io import write_output
from opsicli.opsiservice import get_service_connection

from .common import cli, create_client_depot_mapping, filter_by_attributes, get_validated_ids, process_where
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
	"--where",
	type=str,
	multiple=True,
	help="Filter the output. ObjectId and ConfigId are required",
)
def list_product_property_state(where: tuple[str, ...]) -> None:
	"""
	View all product property states or apply filters to narrow your search.
	"""

	def get_default_property_states(
		object_ids: list[str], product_id: list[str] | None, property_id: list[str] | None
	) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:

		default_property_objects = service_connection.productProperty_getObjects(  # type: ignore[attr-defined]
			productId=product_id,
			productVersion=filter.pop("productVersion", None),
			packageVersion=filter.pop("packageVersion", None),
			propertyId=property_id,
			type=filter.pop("type", None),
			description=filter.pop("description", None),
			editable=forceBool(v) if (v := filter.pop("editable", None)) is not None else None,
			multiValue=forceBool(v) if (v := filter.pop("multiValue", None)) is not None else None,
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

	def update_default_states(
		depot_ids: list[str],
		object_ids: list[str],
		product_id: list[str] | None,
		property_id: list[str] | None,
		default_states: dict[str, dict[str, dict[str, dict[str, Any]]]],
	) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
		depot_property_states = service_connection.productPropertyState_getObjects(  # type: ignore[attr-defined]
			objectId=depot_ids, productId=product_id or [], propertyId=property_id or []
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
						default_states["depotValues"] = depot_values
						default_states["origin"] = "depot"
						if default_states["defaultValues"] != depot_values:
							default_states["values"] = depot_values

		return default_states

	def update_depot_states(
		object_ids: list[str],
		product_ids: list[str] | None,
		property_ids: list[str] | None,
		depot_states: dict[str, dict[str, dict[str, dict[str, Any]]]],
	) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
		client_property_states = service_connection.productPropertyState_getObjects(  # type: ignore[attr-defined]
			objectId=object_ids, productId=product_ids or [], propertyId=property_ids or []
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

	service_connection = get_service_connection()
	metadata = COMMAND_METADATA["datastore_product-property-state_list"]
	attributes = metadata.attributes
	filter = process_where(where, attributes=attributes, operation="list")

	# get Id's from filter
	object_ids = filter.pop("objectId", "*")
	product_ids = filter.pop("productId", "*")
	property_ids = filter.pop("propertyId", "*")

	# validate Id's
	final_object_ids = get_validated_ids(
		service_connection,
		ids=object_ids,
		type="objectId or depotId" if object_ids != "*" else "objectId",  # don't get depotId's if '*'
	)
	final_product_ids = get_validated_ids(service_connection, ids=product_ids, type="productId")
	final_property_ids = get_validated_ids(service_connection, ids=property_ids, type="propertyId")
	final_depot_ids = service_connection.host_getIdents(type="OpsiDepotServer")  # type: ignore[attr-defined]

	# map clients to depots
	client_to_depot = create_client_depot_mapping(service_connection, final_object_ids)

	# get default states and update them
	default_states = get_default_property_states(final_object_ids, final_product_ids, final_property_ids)
	depot_states = update_default_states(final_depot_ids, final_object_ids, final_product_ids, final_property_ids, default_states)
	client_states = update_depot_states(final_object_ids, final_product_ids, final_property_ids, depot_states)

	# prepare data for writing output
	flattened_result: list[dict[str, Any]] = [
		product_property_state
		for product_map in client_states.values()  # objects
		for property_map in product_map.values()  # products
		for product_property_state in property_map.values()  # properties
	]

	filtered_data = filter_by_attributes(flattened_result, filter, attributes)

	# select attributes to display
	for attr in attributes:
		if attr.id in ("objectId", "productId", "propertyId", "values", "origin"):
			attr.selected = True

	write_output(
		data=sorted(filtered_data, key=lambda x: x["objectId"]),
		metadata=metadata,
		value_styles={"depot": "yellow", "client": "blue"},
	)
