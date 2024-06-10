"""
opsi-cli package plugin
"""

from pathlib import Path
from typing import Callable

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger
from opsicommon.package import OpsiPackage
from opsicommon.package.archive import ArchiveProgress, ArchiveProgressListener
from opsicommon.package.associated_files import create_package_md5_file, create_package_zsync_file
from rich.progress import Progress

from opsicli.config import config
from opsicli.io import get_console
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"
__description__ = "Manage opsi packages"


logger = get_logger("opsicli")


def create_additional_file(file_type: str, create_func: Callable, package_archive: Path) -> None:
	logger.info("Creating '%s' for '%s'", file_type, package_archive)
	get_console().print(f"Creating {file_type} for {package_archive}...")
	file = create_func(Path(package_archive))
	get_console().print(f"{file_type} has been successfully created at {file}\n")


class PackageMakeProgressListener(ArchiveProgressListener):
	def __init__(self, progress: Progress, task_message: str):
		self.progress = progress
		self.task_id = self.progress.add_task(task_message, total=100)

	def progress_changed(self, progress: ArchiveProgress) -> None:
		self.progress.update(self.task_id, completed=progress.percent_completed)


@click.group(name="package", short_help="Custom plugin package")
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
	with Progress() as progress:
		progress_listener = None
		if not config.quiet:
			progress_listener = PackageMakeProgressListener(progress, "[cyan]Creating OPSI package...")

		destination_dir.mkdir(parents=True, exist_ok=True)

		logger.info("Creating package archive for '%s'", source_dir)
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
	get_console().print(f"\nPackage archive has been successfully created at {package_archive}\n")
	try:
		if md5:
			create_additional_file("MD5 checksum", create_package_md5_file, package_archive)
		if zsync:
			create_additional_file("zsync file", create_package_zsync_file, package_archive)
	except Exception as err:
		logger.error(err, exc_info=True)
		raise err


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


@cli.command(short_help="Extract an opsi package")
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
			progress_listener = PackageMakeProgressListener(progress, "[cyan]Extracting OPSI package...")
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


class PackagePlugin(OPSICLIPlugin):
	name: str = "Package"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
