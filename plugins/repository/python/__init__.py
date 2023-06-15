"""
opsi-cli repository
"""

from pathlib import Path

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger

from opsicli.plugin import OPSICLIPlugin

from .packages_metadata import PackagesMetadataCollection

__version__ = "0.1.0"
__description__ = "This command manages repositories for opsi packages"


logger = get_logger("opsicli")


@click.group(name="repository", short_help="Custom plugin repository")
@click.version_option(__version__, message="opsi-cli plugin repository, version %(version)s")
@click.pass_context
@click.option(
	"--meta-file",
	help="File to hold repository meta information in",
	default=Path("packages.json"),
	type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
)
def cli(ctx: click.Context, meta_file: Path) -> None:
	"""
	This command manages repositories for opsi packages
	"""
	logger.trace("repository command")
	ctx.obj["meta_file"] = meta_file


@cli.command(short_help="Creates file with repo meta information", name="create-meta-file")
@click.pass_context
@click.argument("path", nargs=1, default=Path(), type=click.Path(file_okay=False, dir_okay=True, path_type=Path))
@click.option(
	"--repository-name",
	help="Name of the repository",
	default="opsi package repository",
	type=str,
)
def create_meta_file(ctx: click.Context, path: Path, repository_name: str) -> None:
	"""
	This subcommand traverses a given path, analyzes all opsi packages it finds
	and stores that information in a structured way in a meta-data file.
	"""
	packages_metadata = PackagesMetadataCollection()
	packages_metadata.collect(path, repository_name)
	packages_metadata.write(ctx.obj["meta_file"])


@cli.command(short_help="Adds or updates section in meta info file", name="add-to-meta-file")
@click.pass_context
@click.argument("package", nargs=1, default=Path(), type=click.Path(file_okay=True, dir_okay=False, path_type=Path))
@click.option(
	"--num-allowed-versions",
	help="This limits the number of kept versions (allows keeping more than 1)",
	default=1,
)
@click.option(
	"--relative-path",
	help="Path to the package relative to the meta file",
	type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
	"--compatibility",
	help="Comma-separated list of operating systems that the package is compatible with",
	type=str,
)
def add_to_meta_file(
	ctx: click.Context, package: Path, num_allowed_versions: int, relative_path: Path | None, compatibility: str | None
) -> None:
	"""
	This subcommand analyzes a given opsi package
	and stores that information in a structured way in an existing meta-data file.
	"""
	packages_metadata = PackagesMetadataCollection(ctx.obj["meta_file"])
	if not relative_path:
		relative_path = package.relative_to(ctx.obj["meta_file"].parent)
	packages_metadata.add_package(
		package, num_allowed_versions=num_allowed_versions, relative_path=relative_path, compatibility=compatibility
	)
	packages_metadata.write(ctx.obj["meta_file"])


@cli.command(short_help="Removes package from meta info file", name="remove-from-meta-file")
@click.pass_context
@click.argument("name", nargs=1, type=str)
@click.argument("version", nargs=1, type=str)
def remove_from_meta_file(ctx: click.Context, name: str, version: str) -> None:
	"""
	This subcommand analyzes a given opsi package
	and stores that information in a structured way in an existing meta-data file.
	"""
	packages_metadata = PackagesMetadataCollection(ctx.obj["meta_file"])
	packages_metadata.remove_package(name, version)
	packages_metadata.write(ctx.obj["meta_file"])


class CustomPlugin(OPSICLIPlugin):
	name: str = "repository"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
