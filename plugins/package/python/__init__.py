"""
opsi-cli package plugin
"""

from contextlib import nullcontext
from pathlib import Path

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger
from opsicommon.objects import OpsiConfigserver, OpsiDepotserver
from opsicommon.package import OpsiPackage
from opsicommon.package.archive import ArchiveProgress, ArchiveProgressListener
from opsicommon.package.associated_files import create_package_md5_file, create_package_zsync_file
from rich.progress import Progress

from opsicli.config import config
from opsicli.io import get_console, write_output
from opsicli.opsiservice import get_depot_connection, get_service_connection
from opsicli.plugin import OPSICLIPlugin
from opsicli.utils import create_nested_dict
from plugins.package.data.metadata import command_metadata

from .install_helpers import (
	check_locked_products,
	fix_custom_package_name,
	install_package,
	sort_packages_by_dependency,
	update_product_properties,
	upload_to_repository,
)

__version__ = "0.2.0"
__description__ = "Manage opsi packages"

logger = get_logger("opsicli")


class PackageMakeProgressListener(ArchiveProgressListener):
	def __init__(self, progress: Progress, task_message: str):
		self.progress = progress
		self.started = False
		self.task_id = self.progress.add_task(task_message, total=None)

	def progress_changed(self, progress: ArchiveProgress) -> None:
		if not self.started:
			self.started = True
			self.progress.tasks[self.task_id].total = 100
		self.progress.update(self.task_id, completed=progress.percent_completed)


class ProgressCallbackAdapter:
	def __init__(self, progress: Progress, task_message: str):
		self.progress = progress
		self.started = False
		self.task_id = self.progress.add_task(task_message, total=None)

	def progress_callback(self, completed: int, total: int) -> None:
		if not self.started:
			self.started = True
			self.progress.tasks[self.task_id].total = total
		self.progress.update(self.task_id, completed=completed)


@click.group(name="package", short_help="Manage opsi packages")
@click.version_option(__version__, message="opsi-cli plugin package, version %(version)s")
def cli() -> None:
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
		progress_listener = None
		if not config.quiet:
			progress_listener = PackageMakeProgressListener(progress, "[cyan]Creating opsi package...")

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
					}
				)
	return combined_products


@cli.command(name="list", short_help="List opsi packages")
@click.option("--depots", help="Depot IDs (comma-separated) or 'all'", default="all")
@click.argument("product_ids", type=str, nargs=-1)
def package_list(depots: str, product_ids: list[str]) -> None:
	"""
	opsi-cli package list subcommand.
	This subcommand is used to list opsi packages.

	A list of product IDs can be specified to filter the output.
	In the product IDs, "*" can be used as a wildcard.
	"""
	logger.trace("list packages")
	depots = depots.strip() or "all"
	depot_list = [depot.strip() for depot in depots.split(",") if depot.strip() != "all"]

	try:
		service_client = get_service_connection()
		product_list = service_client.jsonrpc("product_getObjects")
		product_on_depot_list = service_client.jsonrpc("productOnDepot_getObjects", [[], {"depotId": depot_list, "productId": product_ids}])
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

	with Progress() as progress:
		progress_listener = None
		if not config.quiet:
			progress_listener = PackageMakeProgressListener(progress, "[cyan]Extracting opsi package...")
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


@cli.command(short_help="Install opsi packages.")
@click.argument("opsi_packages", nargs=-1, type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path))
@click.option("--depots", help="Depot IDs (comma-separated) or 'all'. Default is configserver.")
@click.option(
	"--update-properties",
	is_flag=True,
	help="This flag triggers an interactive prompt to update Product property default values.",
)
@click.option("--force", is_flag=True, help="Force installation even if locked products are found.")
def install(opsi_packages: list[str], depots: str, force: bool, update_properties: bool) -> None:
	"""
	opsi-cli package install subcommand.
	This subcommand is used to install opsi packages.
	"""
	logger.trace("install package")

	if not opsi_packages:
		raise click.UsageError("Specify at least one package to install.")

	sorted_opsi_packages = sort_packages_by_dependency(opsi_packages)

	service_client = get_service_connection()
	depot_filter: dict[str, str | list[str]] = (
		{"type": "OpsiDepotserver"}
		if depots == "all"
		else {"id": [depot.strip() for depot in depots.split(",")]}
		if depots
		else {"type": "OpsiConfigserver"}
	)
	depot_objects: list[OpsiConfigserver | OpsiDepotserver] = service_client.jsonrpc("host_getObjects", [[], depot_filter])

	check_locked_products(service_client, sorted_opsi_packages, depot_objects, force)

	if update_properties:
		for package in sorted_opsi_packages:
			opsi_package = OpsiPackage(package)
			update_product_properties(opsi_package)

	for depot in depot_objects:
		depot_connection = get_depot_connection(depot)
		for package in sorted_opsi_packages:
			dest_package_name = fix_custom_package_name(package)
			upload_to_repository(depot_connection, depot, package, dest_package_name)
			install_package(depot_connection, depot, package, dest_package_name, update_properties, service_client)


class PackagePlugin(OPSICLIPlugin):
	name: str = "Package"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
