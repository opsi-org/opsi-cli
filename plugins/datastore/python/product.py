# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

config-states subcommand
"""

import rich_click as click
from opsicommon.logging import get_logger

from opsicli.decorators import dry_run_capable
from opsicli.io import OutputType, console_print, get_separated_entries
from opsicli.opsiservice import config, get_service_connection

from .common import cli, process_where
from .metadata import COMMAND_METADATA

logger = get_logger("opsicli")


@cli.group(name="product", short_help="Manage products.")
def product() -> None:
	"""
	Manage products.
	"""
	pass


@product.command(name="unlock", short_help="Unlock products on depots.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter products.",
)
@dry_run_capable
def product_unlock(where: tuple[str, ...]) -> None:
	"""
	Remove locks from products on specified depots.
	"""

	# Helper function, get products, unlock them, update them
	def unlock_and_update(product_ids: list[str], depot_ids: list[str]) -> None:
		service_connection = get_service_connection()
		product_on_depots = service_connection.productOnDepot_getObjects(productId=product_ids, depotId=depot_ids or [])  # type: ignore[attr-defined]

		# empty result
		if not product_on_depots:
			logger.error("No such depot(s): %s", depot_ids)
			raise ValueError("No products found matching the filtering criteria.")
		for product_on_depot in product_on_depots:
			product_on_depot.locked = False
		service_connection.productOnDepot_updateObjects(product_on_depots)  # type: ignore[attr-defined]

	filter = process_where(where, attributes=COMMAND_METADATA["datastore_product_unlock"].attributes, operation="unlock")
	filter = {k: (v if v != "*" else None) for k, v in filter.items()}

	product_ids_list = get_separated_entries(filter.pop("productId", None))
	depot_ids_list = get_separated_entries(filter.pop("depotId", None))

	if config.dry_run:
		msg = f"Unlocking skipped due to dry run. Here are the products that would have been unlocked:\n{product_ids_list}"
	else:
		unlock_and_update(product_ids_list, depot_ids_list)  # type: ignore[invalid-argument-type]
		msg = f"Products unlocked successfully. Here are the unlocked products:\n{product_ids_list}"

	console_print(msg, style="green", output_type=OutputType.MESSAGE)


@product.command(name="purge", short_help="Purge metadata related to uninstalled products.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter products.",
)
@dry_run_capable
def product_purge(where: tuple[str, ...]) -> None:
	"""
	Remove metadata associated with uninstalled products, such as installation status and product property states.

	"""
	service_connection = get_service_connection()
	filter = process_where(where, attributes=COMMAND_METADATA["datastore_product_purge"].attributes, operation="purge")
	# process wildcards
	filter = {k: (v if v != "*" else None) for k, v in filter.items()}

	product_id_list = service_connection.product_getIdents(get_separated_entries(filter.pop("productId", None)))  # type: ignore[attr-defined]

	# empty result
	if not product_id_list:
		raise ValueError("No products found matching the filtering criteria.")

	if config.dry_run:
		msg = f"Purge skipped due to dry run. Here are the products that would have been purged:\n{product_id_list}"
	else:
		msg = f"Products purged successfully. Here are the purged products:\n{product_id_list}"
		service_connection.product_purge(id=product_id_list)  # type: ignore[attr-defined]

	console_print(msg, style="green", output_type=OutputType.MESSAGE)
