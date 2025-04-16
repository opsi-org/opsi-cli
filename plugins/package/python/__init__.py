# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli package plugin
"""

import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Literal

import rich_click as click
from click.shell_completion import CompletionItem
from opsicommon.logging import get_logger
from opsicommon.objects import ProductOnDepot
from opsicommon.package import OpsiPackage
from opsicommon.package.associated_files import create_package_md5_file, create_package_zsync_file
from opsicommon.utils import make_temp_dir
from rich.progress import Progress

from opsicli.config import config
from opsicli.decorators import handle_list_attributes
from opsicli.io import get_console, write_output
from opsicli.opsiservice import get_depot_connection, get_service_connection
from opsicli.plugin import OPSICLIPlugin
from opsicli.utils import ProgressCallbackAdapter, create_nested_dict
from plugins.package.data.metadata import command_metadata

from .package_helpers import (
	check_locked_products,
	cleanup_packages_from_repo,
	fix_custom_package_name,
	get_depot_objects,
	get_product_on_depot_objects,
	handle_action_request,
	install_package,
	map_and_sort_packages,
	process_local_packages,
	uninstall_package,
	update_product_property_defaults_interactively,
	upload_to_repository,
)
from .package_progress import PackageProgressListener

__version__ = "0.2.0"
__description__ = "Manage opsi packages"

logger = get_logger("opsicli")


@click.group(name="package", short_help="Manage opsi packages")
@click.version_option(__version__, message="opsi-cli plugin package, version %(version)s")
@click.pass_context
@handle_list_attributes
def cli(ctx: click.Context) -> None:
	"""
	opsi-cli package command.
	This command is used to manage opsi packages.
	"""
	logger.trace("package command")


@cli.command(short_help="Create an opsi package")
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path), default=Path("."))
@click.argument("destination_dir", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), default=Path("."))
@click.option("-o", "--overwrite", is_flag=True, default=False, help="Overwrite existing package if it exists.")
@click.option("--follow-symlinks", is_flag=True, help="Flag to follow symlinks", default=False)
@click.option("--custom-name", type=str, help="Custom name for directories", default=None)
@click.option("--custom-only", is_flag=True, help="Flag to use only custom directories", default=False)
@click.option("--md5/--no-md5", is_flag=True, help="Flag to create md5 checksum for the package", default=True)
@click.option("--zsync/--no-zsync", is_flag=True, help="Flag to create zsync file for the package", default=True)
def make(
	source_dir: Path,
	destination_dir: Path,
	overwrite: bool,
	follow_symlinks: bool,
	custom_name: str,
	custom_only: bool,
	md5: bool,
	zsync: bool,
) -> None:
	"""
	opsi-cli package make subcommand.
	This subcommand is used to create an opsi package.
	"""
	logger.trace("make package")
	with nullcontext() if config.quiet else Progress() as progress:  # type: ignore[attr-defined]
		assert progress
		progress_listener = None
		if not config.quiet:
			progress_listener = PackageProgressListener(progress, "[cyan]Creating opsi package...")

		destination_dir.mkdir(parents=True, exist_ok=True)

		logger.info("Creating opsi package from source dir '%s'", source_dir)
		opsi_package = OpsiPackage()
		try:
			package_archive = opsi_package.create_package_archive(
				source_dir,
				destination=destination_dir,
				progress_listener=progress_listener,
				overwrite=overwrite,
				dereference=follow_symlinks,
				custom_name=custom_name,
				custom_only=custom_only,
			)
		except Exception as err:
			logger.error(err, exc_info=True)
			raise err

		md5_file: Path | None = None
		zsync_file: Path | None = None
		try:
			if md5:
				logger.info("Creating md5sum file for '%s'", package_archive)
				progress_callback = (
					ProgressCallbackAdapter(progress, "[cyan]Creating md5sum file...").progress_callback if not config.quiet else None
				)
				md5_file = create_package_md5_file(package_archive, progress_callback=progress_callback)
			if zsync:
				logger.info("Creating zsync file for '%s'", package_archive)
				progress_callback = (
					ProgressCallbackAdapter(progress, "[cyan]Creating zsync file...").progress_callback if not config.quiet else None
				)
				zsync_file = create_package_zsync_file(package_archive, progress_callback=progress_callback)
		except Exception as err:
			logger.error(err, exc_info=True)
			raise err

	console = get_console()
	console.print(f"The opsi package was created at '{package_archive}'")
	if md5_file:
		console.print(f"The md5sum file was created at '{md5_file}'")
	if zsync_file:
		console.print(f"The zsync file was created at '{zsync_file}'")


def combine_products(product_dict: dict, product_on_depot_dict: dict) -> list:
	"""
	Returns a list of dictionaries, each has combined product and product on depot information
	"""
	combined_products = []
	for depot_id, products in product_on_depot_dict.items():
		for product_id in sorted(products):
			pod = products[product_id]
			product = product_dict.get(pod.productId, {}).get(pod.productVersion, {}).get(pod.packageVersion)
			if product:
				combined_products.append(
					{
						"depot_id": depot_id,
						"product_id": product_id,
						"name": product.name,
						"description": product.description,
						"product_version": product.productVersion,
						"package_version": product.packageVersion,
						"product_type": pod.productType,
					}
				)
	return combined_products


@cli.command(name="list", short_help="List opsi packages")
@click.option("--depots", help="Depot IDs (comma-separated) or 'all'", default="all")
@click.option(
	"--product-type",
	type=click.Choice(["localboot", "netboot"], case_sensitive=False),
	help="Filter by product type",
	default=None,
)
@click.argument("product_ids", type=str, nargs=-1)
def package_list(depots: str, product_type: str, product_ids: list[str]) -> None:
	"""
	opsi-cli package list subcommand.
	This subcommand is used to list opsi packages.

	A list of product IDs can be specified to filter the output.
	In the product IDs, "*" can be used as a wildcard.
	"""
	logger.trace("list packages")
	depots = depots.strip() or "all"
	depot_list = [depot.strip() for depot in depots.split(",") if depot.strip() != "all"]

	if product_type:
		product_type = {"localboot": "LocalbootProduct", "netboot": "NetbootProduct"}.get(product_type.lower(), product_type)

	try:
		service_client = get_service_connection()
		product_list = service_client.jsonrpc("product_getObjects", [[], {"id": product_ids, "type": product_type}])
		product_on_depot_list = service_client.jsonrpc(
			"productOnDepot_getObjects", [[], {"depotId": depot_list, "productId": product_ids, "productType": product_type}]
		)
	except Exception as err:
		logger.error(err, exc_info=True)
		raise err

	product_dict = create_nested_dict(product_list, ["id", "productVersion", "packageVersion"])
	product_on_depot_dict = create_nested_dict(product_on_depot_list, ["depotId", "productId"])

	combined_products = combine_products(product_dict, product_on_depot_dict)
	metadata = command_metadata.get("package_list")
	write_output(combined_products, metadata=metadata, default_output_format="table")


@cli.command(short_help="Generate TOML from control file.")
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path), default=Path("."))
def control_to_toml(source_dir: Path) -> None:
	"""
	opsi-cli package control_to_toml subcommand.
	This subcommand is used to generate a TOML file from a control file.
	"""
	logger.trace("control-to-toml")

	opsi_package = OpsiPackage()
	try:
		control_file = opsi_package.find_and_parse_control_file(source_dir)
		control_toml = control_file.with_suffix(".toml")
		if control_toml.exists():
			raise FileExistsError(f"Control TOML '{control_toml}' already exists.")
		opsi_package.generate_control_file(control_toml)
	except Exception as err:
		logger.error(err, exc_info=True)
		raise err

	get_console().print("Control TOML has been successfully generated.\n")


@cli.command(short_help="Extract an opsi package.")
@click.argument("package_archive", type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path))
@click.argument("destination_dir", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), default=Path("."))
@click.option(
	"--new-product-id",
	type=str,
	default=None,
	help="A new product ID to replace the existing one in the control file.",
)
@click.option("-o", "--overwrite", is_flag=True, default=False, help="Overwrite destination directory if it exists.")
def extract(package_archive: Path, destination_dir: Path, new_product_id: str, overwrite: bool) -> None:
	"""
	opsi-cli package extract subcommand.
	This subcommand is used to extract an opsi package.
	"""
	logger.trace("extract package")

	package_name = package_archive.stem
	destination_dir = destination_dir / package_name
	if not overwrite and destination_dir.exists():
		raise FileExistsError(f"Destination directory '{destination_dir}' already exists.")
	destination_dir.mkdir(parents=True, exist_ok=True)

	with nullcontext() if config.quiet else Progress() as progress:  # type: ignore[attr-defined]
		assert progress
		progress_listener = None
		if not config.quiet:
			progress_listener = PackageProgressListener(progress, "[cyan]Extracting opsi package...")
		logger.info("Extracting package archive for '%s'", destination_dir)
		opsi_package = OpsiPackage()
		try:
			opsi_package.extract_package_archive(
				Path(package_archive),
				destination=destination_dir,
				new_product_id=new_product_id,
				progress_listener=progress_listener,
				custom_separated=True,
			)
		except Exception as err:
			logger.error(err, exc_info=True)
			raise err

	get_console().print(f"Package archive has been successfully extracted at {destination_dir}\n")


def complete_package_path(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[CompletionItem]:
	"""
	Completes the package archive file paths from the current directory or a user-specified directory.
	"""
	base_dir = Path(incomplete).parent if "/" in incomplete else Path(".")
	base_dir = base_dir.resolve()
	archive_extensions = [".opsi", ".tar.gz", ".zip", ".tgz", ".tar.bz2", ".tbz", ".tar.xz", ".txz"]
	if base_dir.is_dir():
		return [CompletionItem(str(file)) for ext in archive_extensions for file in base_dir.glob(f"*{Path(incomplete).name}*{ext}")]
	return []


@cli.command(short_help="Install opsi packages.")
@click.argument("packages", nargs=-1, required=True, type=str, shell_complete=complete_package_path)
@click.option("--depots", help="Depot IDs (comma-separated) or 'all'. Default is configserver.")
@click.option(
	"--update-properties",
	is_flag=True,
	help="Deprecated, please use `--properties ask`.",
	default=False,
)
@click.option(
	"--properties",
	type=click.Choice(["keep", "ask", "package"], case_sensitive=False),
	help=(
		"How to handle product property default values."
		"'keep' the current defaults, 'ask' for values interactively or use the defaults from the 'package'. The default is 'keep'."
	),
	default="keep",
)
@click.option("--force", is_flag=True, help="Force installation.", default=False)
@click.option("--setup-where-installed", is_flag=True, help="Setup where installed.", default=False)
@click.option("--setup-where-installed-with-dependencies", is_flag=True, help="Setup where installed with dependencies.", default=False)
@click.option("--update-where-installed", is_flag=True, help="Update where installed.", default=False)
def install(
	packages: list[str],
	depots: str,
	force: bool,
	update_properties: bool,
	properties: Literal["keep", "ask", "package"],
	setup_where_installed: bool,
	setup_where_installed_with_dependencies: bool,
	update_where_installed: bool,
) -> None:
	"""
	opsi-cli package install subcommand.
	This subcommand is used to install opsi packages.
	"""
	logger.trace("install package")
	if update_properties:
		console = get_console(file=sys.stderr)
		console.print(
			"[bright_yellow]The `--update-properties` option is deprecated, please use `--properties ask` instead.[/bright_yellow]\n"
		)
		properties = "ask"

	service_client = get_service_connection()
	with make_temp_dir() as temp_dir:
		local_packages = process_local_packages(packages, temp_dir)
		# path_to_opsipackage maps package paths to OpsiPackage objects (metadata)
		path_to_opsipackage = map_and_sort_packages(local_packages)
		depot_objects = get_depot_objects(service_client, depots)

		if not force:
			check_locked_products(service_client, depot_objects, path_to_opsipackage)

		if properties == "ask":
			if not config.interactive:
				raise click.UsageError("Using --properties=ask is not possible in non-interactive mode.")

			update_product_property_defaults_interactively(path_to_opsipackage)

		for depot in depot_objects:
			depot_connection = get_depot_connection(depot)
			try:
				for package_path, opsi_package in path_to_opsipackage.items():
					dest_package_name = fix_custom_package_name(package_path)
					upload_to_repository(depot_connection, depot.id, package_path, dest_package_name, temp_dir)

					property_default_values = {
						product_property.propertyId: product_property.defaultValues or []
						for product_property in opsi_package.product_properties
					}
					if properties == "keep":
						# Keep current property default values set on depot
						for product_property_state in service_client.jsonrpc(
							"productPropertyState_getObjects",
							[[], {"productId": opsi_package.product.id, "objectId": depot.id}],
						):
							property_default_values[product_property_state.propertyId] = product_property_state.values or []

					install_package(depot_connection, depot.id, dest_package_name, force, property_default_values)

					if setup_where_installed or setup_where_installed_with_dependencies or update_where_installed:
						action_request = "update" if update_where_installed else "setup"
						dependency = setup_where_installed_with_dependencies if setup_where_installed_with_dependencies else False
						handle_action_request(service_client, depot.id, opsi_package.product, action_request, dependency)
			finally:
				depot_connection.disconnect()


def complete_installed_products(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[CompletionItem]:
	"""
	Suggests installed products from the selected depots, limited to a maximum of 10 results.
	"""
	MAX_RESULTS = 10
	service_client = get_service_connection()
	depots = ctx.params.get("depots", "all")
	depot_list = [depot.id for depot in get_depot_objects(get_service_connection(), depots)]
	installed_packages = get_product_on_depot_objects(service_client, tuple(depot_list))
	suggestions = [CompletionItem(pod["productId"]) for pod in installed_packages if pod["productId"].startswith(incomplete)]
	return suggestions[:MAX_RESULTS]


@cli.command(short_help="Uninstall opsi products.")
@click.argument("product_ids", type=str, nargs=-1, required=True, shell_complete=complete_installed_products)
@click.option("--depots", help="Depot IDs (comma-separated) or 'all'. Default is configserver.")
@click.option("--force", is_flag=True, help="Force uninstallation.", default=False)
@click.option("--keep-files", is_flag=True, help="Keep files on uninstallation.", default=False)
def uninstall(product_ids: list[str], depots: str, force: bool, keep_files: bool) -> None:
	"""
	opsi-cli package uninstall subcommand.
	This subcommand is used to uninstall opsi products.
	"""
	logger.trace("uninstall package")

	service_client = get_service_connection()
	depot_objects = get_depot_objects(service_client, depots)

	depot_list = [depot.id for depot in depot_objects]
	product_on_depot_list: list[ProductOnDepot] = service_client.jsonrpc(
		"productOnDepot_getObjects", [[], {"depotId": depot_list, "productId": product_ids}]
	)
	if not product_on_depot_list:
		raise click.UsageError("No products found to uninstall.")

	for depot in depot_objects:
		depot_connection = get_depot_connection(depot)
		try:
			for product_on_depot in product_on_depot_list:
				cleanup_packages_from_repo(depot_connection, product_on_depot.productId)
				uninstall_package(depot_connection, depot.id, product_on_depot.productId, force, not keep_files)
		finally:
			depot_connection.disconnect()


class PackagePlugin(OPSICLIPlugin):
	name: str = "Package"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
