# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import cast

import rich_click as click
from opsi.logging import get_logger
from opsi.opsi.service.model.object import ProductOnClient
from opsi.opsi.service.model.type import to_action_request, to_installation_status

from opsicli.config import config
from opsicli.decorators import dry_run_capable, mutually_exclusive
from opsicli.io import OutputType, console_print, get_separated_entries, read_input, write_output
from opsicli.opsiservice import get_service_connection

from .common import cli, filter_by_attributes, get_depot_to_clients, process_where
from .metadata import COMMAND_METADATA

logger = get_logger("opsicli")


@cli.group(name="product-client-state", short_help="Manage product states of clients.")
def product_client_state() -> None:
	"""
	View and change product states of clients.
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


@product_client_state.command(name="list", short_help="List product states of clients.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter product-client-states by their attributes.",
)
@click.option(
	"--all",
	is_flag=True,
	help="Show every product state for every client.",
)
@mutually_exclusive("where", "all")
def list_product_client_state(where: tuple[str, ...], all: bool) -> None:
	"""
	List all product states or apply filters to narrow the result.
	"""
	service_connection = get_service_connection()
	metadata = COMMAND_METADATA["datastore_product-client-state_list"]
	if not all:
		filter = process_where(where, attributes=metadata.attributes, operation="list")
		filter = {k: (v if v != "*" else "") for k, v in filter.items()}  # process wildcards
	else:
		filter = {}

	filter_client_ids = service_connection.host_getIdents(id=get_separated_entries(filter.pop("clientId", None)), type="OpsiClient")  # ty: ignore[unresolved-attribute]
	filter_product_ids = get_separated_entries(filter.pop("productId", None))

	tmp_list = get_separated_entries(filter.pop("installationStatus", None))
	if not tmp_list:
		filter_installation_statuses = ["installed", "not_installed", "unknown"]
	else:
		filter_installation_statuses = [to_installation_status(item) for item in tmp_list]

	tmp_list = get_separated_entries(filter.pop("actionRequest", None))
	if not tmp_list:
		filter_action_requests = ["setup", "uninstall", "update", "always", "once", "custom", "none"]
	else:
		filter_action_requests = [to_action_request(item) for item in tmp_list]

	product_states: dict[str, ProductClientState] = {}
	if "none" in filter_action_requests and "not_installed" in filter_installation_statuses:
		depot_to_clients = get_depot_to_clients(service_connection, filter_client_ids)
		depot_ids = list(depot_to_clients)
		for pod in service_connection.productOnDepot_getIdents(returnType="dict", productId=filter_product_ids, depotId=depot_ids):  # ty: ignore[unresolved-attribute]
			for client_id in depot_to_clients.get(pod["depotId"], []):
				product_states[f"{client_id};{pod['productId']}"] = ProductClientState(
					productType=pod["productType"],
					productId=pod["productId"],
					clientId=client_id,
					installationStatus="not_installed",
					actionRequest="none",
				)

	for poc in service_connection.productOnClient_getObjects(  # ty: ignore[unresolved-attribute]
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

	# filter by remaining attributes
	result_as_dicts = [asdict(state) for state in product_states.values()]
	filtered_data = filter_by_attributes(data=result_as_dicts, attributes=metadata.attributes, filter=filter)

	# empty result
	if not filtered_data:
		raise ValueError("No product-client-states found matching the filtering criteria.")

	write_output(
		# data=sorted(filtered_data, key=lambda x: x["clientId"]),
		data=filtered_data,
		metadata=COMMAND_METADATA.get("datastore_product-client-state_list"),
		value_styles=PRODUCT_CLIENT_STATE_VALUE_STYLES,
	)


@product_client_state.command(name="update", short_help="Update product states of clients.")
@dry_run_capable
def update_product_client_state() -> None:
	"""
	Update product states of clients.
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
				installationStatus=to_installation_status(product_state.get("installationStatus") or "not_installed"),
				actionRequest=to_action_request(product_state.get("actionRequest") or "none") or "none",
				modificationTime=modification_time,
			)
		)

	if not pcs:
		raise ValueError("No product-client-states found matching the filtering criteria.")
	if config.dry_run:
		msg = "Update skipped due to dry run. Here are the product client states that would have been updated:\n"
	else:
		service_connection = get_service_connection()
		service_connection.productOnClient_updateObjects(pcs)  # ty: ignore[unresolved-attribute]
		msg = "Product client states updated successfully. Here are the updated states:\n"

	console_print(msg, style="green", output_type=OutputType.MESSAGE)
	write_output(
		data=pcs,
		metadata=COMMAND_METADATA["datastore_product-client-state_list"],
		value_styles=PRODUCT_CLIENT_STATE_VALUE_STYLES,
	)
