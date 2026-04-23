# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

config-states subcommand
"""

import rich_click as click
from opsicommon.exceptions import BackendMissingDataError
from opsicommon.logging import get_logger

from opsicli.io import OutputType, console_print
from opsicli.opsiservice import get_service_connection

from .common import cli

logger = get_logger("opsicli")


@cli.group(name="product", short_help="Manage products.")
def product() -> None:
	"""
	Manage products.
	"""
	pass


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
	unlock_and_update(product_ids_list, depot_ids_list)  # type: ignore[invalid-argument-type]


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
