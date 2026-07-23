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
from plugins.datastore.data.help_texts import PRODUCT_HELP as info
from plugins.datastore.data.messages import Error, Status

from .common import cli, process_where
from .metadata import COMMAND_METADATA

logger = get_logger("opsicli")


# Helper function: get products -> unlock them -> update them
def _unlock_and_update(product_ids: list[str], depot_ids: list[str]) -> None:
	service_connection = get_service_connection()
	product_on_depots = service_connection.productOnDepot_getObjects(productId=product_ids, depotId=depot_ids)  # ty: ignore[unresolved-attribute]

	# unlock
	for product_on_depot in product_on_depots:
		product_on_depot.locked = False
	# update
	service_connection.productOnDepot_updateObjects(product_on_depots)  # ty: ignore[unresolved-attribute]


@cli.group(name="product", short_help=info.GENERAL.short, help=info.GENERAL.long)
def product() -> None:
	pass


@product.command(name="unlock", short_help=info.UNLOCK.short, help=info.UNLOCK.long)
@click.option(
	"--where",
	type=str,
	multiple=True,
	help=info.UNLOCK.where,
)
@click.option(
	"--all",
	is_flag=True,
	help=info.UNLOCK.all,
)
@mutually_exclusive("all", "where")
@dry_run_capable
def product_unlock(where: tuple[str, ...], all: bool) -> None:
	service_connection = get_service_connection()
	available_depot_ids = service_connection.host_getIdents(id=[], type="OpsiDepotserver")  # ty: ignore[unresolved-attribute]
	if all:
		product_ids = []
		depot_ids = []
		filter = None
	else:
		filter = process_where(where, attributes=COMMAND_METADATA["datastore_product_unlock"].attributes, operation="unlock")
		product_ids = get_separated_entries(filter.get("productId", None))
		depot_ids = get_separated_entries(filter.get("depotId", None))

	final_depot_ids = service_connection.host_getIdents(id=depot_ids, type="OpsiDepotserver")  # ty: ignore[unresolved-attribute]
	product_idents = service_connection.productOnDepot_getIdents(productId=product_ids, depotId=final_depot_ids)  # ty: ignore[unresolved-attribute]
	final_product_ids = [id.split(";")[0] for id in product_idents]

	# help for wrong depotId
	if not final_depot_ids and filter:
		raise ValueError(
			Error.invalid_value_where(available_values=available_depot_ids, attribute="depotId", value=filter.get("depotId", ""))
		)

	# empty result
	if not final_product_ids:
		raise ValueError(Error.no_match())

	if not config.dry_run:
		_unlock_and_update(final_product_ids, final_depot_ids)
		msg = Status.success()
	else:
		msg = Status.dry_run()

	console_print(msg, style="green", output_type=OutputType.MESSAGE)
	write_output(data=final_product_ids, metadata=COMMAND_METADATA["datastore_product_unlock"])


@product.command(name="purge", short_help=info.PURGE.short, help=info.PURGE.long)
@click.option("--where", type=str, multiple=True, help=info.PURGE.where)
@click.option(
	"--all",
	is_flag=True,
	help=info.PURGE.all,
)
@dry_run_capable
@mutually_exclusive("all", "where")
def product_purge(where: tuple[str, ...], all: bool) -> None:
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
		raise ValueError(Error.no_match())

	if config.dry_run:
		msg = Status.dry_run()
	else:
		msg = Status.success()
		service_connection.product_purge(id=product_ids)  # ty: ignore[unresolved-attribute]

	console_print(msg, style="green", output_type=OutputType.MESSAGE)
	write_output(data=product_ids, metadata=COMMAND_METADATA["datastore_product_purge"])
