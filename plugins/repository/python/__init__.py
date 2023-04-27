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
def cli() -> None:
	"""
	This command manages repositories for opsi packages
	"""
	logger.trace("repository command")


@cli.command(short_help="Some example subcommand", name="create-meta-file")
@click.argument("path", nargs=1, default=Path(), type=click.Path(file_okay=False, dir_okay=True, path_type=Path))
@click.option(
	"--output-file",
	help="File to store the output in",
	default=Path("packages.json"),
	type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
	"--repository-name",
	help="Name of the repository",
	default="opsi package repository",
	type=str,
)
def create_meta_file(path: Path, output_file: Path, repository_name: str) -> None:
	"""
	This subcommand traverses a given path, analyzes all opsi packages it finds
	and stores that information in a structured way in a meta-data file.
	"""
	packages_metadata = PackagesMetadataCollection(repository_name)
	packages_metadata.collect(path)
	packages_metadata.write(output_file)


# This class keeps track of the plugins meta-information
class CustomPlugin(OPSICLIPlugin):
	name: str = "repository"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = []
