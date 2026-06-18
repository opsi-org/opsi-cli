# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

config-states subcommand
"""

import rich_click as click
from opsi.logging import get_logger

from opsicli.decorators import dry_run_capable, mutually_exclusive
from opsicli.io import OutputType, console_print, get_separated_entries, write_output
from opsicli.opsiservice import config, get_service_connection

from .common import cli, process_where
from .metadata import COMMAND_METADATA

logger = get_logger("opsicli")


@cli.group(name="product", short_help="Manage local OPSI software products and repository states.")
def product() -> None:
	"""
	Unlock locked software products or clean up tracking data for uninstalled OPSI packages.
	"""
	pass


@product.command(name="unlock", short_help="Unlock locked software products on specific depot servers.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Target a specific product and depot to unlock (e.g., --where 'productId=firefox' --where 'depotId=depot1.domain.local').",
)
@click.option(
	"--all",
	is_flag=True,
	help="Unlock all products across every single depot server globally.",
)
@mutually_exclusive("all", "where")
@dry_run_capable
def product_unlock(where: tuple[str, ...], all: bool) -> None:
	"""
	Remove locks from OPSI product packages on your depot servers.
	This allows stuck or interrupted package distributions to resume.
	"""

	# Helper function, get products, unlock them, update them
	def unlock_and_update(product_ids: list[str], depot_ids: list[str]) -> None:
		service_connection = get_service_connection()
		product_on_depots = service_connection.productOnDepot_getObjects(productId=product_ids, depotId=depot_ids)  # ty: ignore[unresolved-attribute]

		# empty result
		if not product_on_depots:
			logger.error("No such depot(s): %s", depot_ids)
			raise ValueError("No products found matching the filtering criteria.")
		for product_on_depot in product_on_depots:
			product_on_depot.locked = False
		service_connection.productOnDepot_updateObjects(product_on_depots)  # ty: ignore[unresolved-attribute]

	service_connection = get_service_connection()
	if not all:
		filter = process_where(where, attributes=COMMAND_METADATA["datastore_product_unlock"].attributes, operation="unlock")
		filter = {k: (v if v != "*" else None) for k, v in filter.items()}
	else:
		filter = {}

	product_idents = service_connection.product_getIdents(id=get_separated_entries(filter.pop("productId", None)))  # ty: ignore[unresolved-attribute]
	product_ids = [id.split(";")[0] for id in product_idents]
	depot_ids = service_connection.host_getIdents(id=get_separated_entries(filter.pop("depotId", None)), type="OpsiDepotserver")  # ty: ignore[unresolved-attribute]

	if not product_ids or not depot_ids:  # empty result
		raise ValueError("No products found matching the filtering criteria.")

	if config.dry_run:
		msg = "Unlocking skipped due to dry run. Here are the products that would have been unlocked:\n"
	else:
		unlock_and_update(product_ids, depot_ids)
		msg = "Products unlocked successfully. Here are the unlocked products:\n"

	console_print(msg, style="green", output_type=OutputType.MESSAGE)
	write_output(data=product_ids, metadata=COMMAND_METADATA["datastore_product_purge"])


@product.command(name="purge", short_help="Completely purge backend database traces of uninstalled products.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter by specific OPSI product IDs to purge (e.g., --where 'productId=old-java-package').",
)
@click.option(
	"--all",
	is_flag=True,
	help="Wipe historical data for all products that are no longer installed anywhere or present on any depot server.",
)
@dry_run_capable
@mutually_exclusive("all", "where")
def product_purge(where: tuple[str, ...], all: bool) -> None:
	"""
	Run database garbage collection to permanently delete old installation records and product property assignments
	for software products that have been uninstalled and removed from your OPSI server.
	"""
	service_connection = get_service_connection()

	if not all:
		filter = process_where(where, attributes=COMMAND_METADATA["datastore_product_purge"].attributes, operation="purge")
		filter = {k: (v if v != "*" else "") for k, v in filter.items()}  # process wildcards
	else:
		filter = {}
	product_idents = service_connection.product_getIdents(get_separated_entries(filter.pop("productId", None)))  # ty: ignore[unresolved-attribute]
	product_ids = [id.split(";")[0] for id in product_idents]
	# empty result
	if not product_ids:
		raise ValueError("No products found matching the filtering criteria.")

	if config.dry_run:
		msg = "Purge skipped due to dry run. Here are the products that would have been purged:\n"
	else:
		msg = "Products purged successfully. Here are the purged products:\n"
		service_connection.product_purge(id=product_ids)  # ty: ignore[unresolved-attribute]

	console_print(msg, style="green", output_type=OutputType.MESSAGE)
	write_output(data=product_ids, metadata=COMMAND_METADATA["datastore_product_purge"])
