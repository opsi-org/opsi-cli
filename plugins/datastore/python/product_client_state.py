# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.objects import ProductOnClient
from opsicommon.types import forceActionRequest, forceInstallationStatus

from opsicli.config import config
from opsicli.decorators import dry_run_capable
from opsicli.io import OutputType, console_print, read_input, write_output
from opsicli.opsiservice import get_service_connection

from .common import cli, get_depot_to_clients, get_object_ids
from .metadata import COMMAND_METADATA

logger = get_logger("opsicli")


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
		metadata=COMMAND_METADATA.get("datastore_product-client-state_list"),
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
		metadata=COMMAND_METADATA["datastore_product-client-state_list"],
		value_styles=PRODUCT_CLIENT_STATE_VALUE_STYLES,
	)
