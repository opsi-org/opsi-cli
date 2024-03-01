"""
opsi-cli manage-repo
"""

from pathlib import Path

import requests  # type: ignore[import]
import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger
from opsicommon.package.repo_meta import (
	RepoMetaPackage,
	RepoMetaPackageCollection,
	RepoMetaPackageCompatibility,
)

from opsicli.plugin import OPSICLIPlugin

__version__ = "0.2.0"
__description__ = "This command manages repositories for opsi packages"


logger = get_logger("opsicli")


CHANGELOG_SERVER = "https://changelog.opsi.org"


def url_exists(url: str) -> bool:
	result = requests.head(url, timeout=(5, 5))
	return result.status_code >= 200 and result.status_code < 300


def add_changelog_and_releasenote_url(package: RepoMetaPackage) -> None:
	base_url = f"{CHANGELOG_SERVER}/OPSI_PACKAGE/{package.product_id}"
	changelog_url = f"{base_url}/changelog.txt"
	release_notes_url = f"{base_url}/release_notes.txt"
	if url_exists(changelog_url):
		package.changelog_url = changelog_url
	if url_exists(release_notes_url):
		package.release_notes_url = release_notes_url


@click.group(name="manage-repo", short_help="opsi-package-repository management.")
@click.version_option(__version__, message="opsi-cli opsi-package-repository management, version %(version)s")
def cli() -> None:
	"""
	This command manages repositories for opsi packages
	"""
	logger.trace("manage-repo command")


@cli.group(name="metafile", short_help="opsi-package-repository metadata file management")
def metafile() -> None:
	"""
	This command manages metafile in repositories for opsi packages
	"""
	logger.trace("metafile command")


argument_directory = click.argument(
	"directory", nargs=1, default=Path("."), type=click.Path(file_okay=False, dir_okay=True, path_type=Path)
)
option_format = click.option(
	"--format",
	help="Meta data file format",
	multiple=True,
	default=["json", "msgpack.zstd"],
	type=click.Choice(["json", "msgpack", "json.zstd", "msgpack.zstd"], case_sensitive=True),
)
option_repository_name = click.option(
	"--repository-name",
	help="Name of the repository",
	type=str,
)
option_scan = click.option(
	"--scan", help="Scan for packages and update package information in metafile.", is_flag=True, type=bool, required=False, default=False
)


def _metafile_update(
	directory: Path, read: bool, format: list[str] | None = None, repository_name: str | None = None, scan: bool = False
) -> None:
	current_meta_files = list(directory.glob("packages.*"))
	packages_metadata = RepoMetaPackageCollection()
	if read and current_meta_files:
		packages_metadata.read_metafile(current_meta_files[0])
	if repository_name:
		packages_metadata.repository.name = repository_name
	if scan:
		packages_metadata.scan_packages(directory, add_callback=add_changelog_and_releasenote_url)

	if format:
		for suffix in format:
			metadata_file = directory / f"packages.{suffix}"
			if metadata_file in current_meta_files:
				current_meta_files.remove(metadata_file)
			packages_metadata.write_metafile(metadata_file)

		for meta_file in current_meta_files:
			meta_file.unlink()
	else:
		for metadata_file in current_meta_files:
			packages_metadata.write_metafile(metadata_file)


@metafile.command(short_help="Creates repository metadata files.", name="create")
@argument_directory
@option_format
@option_repository_name
@option_scan
def metafile_create(directory: Path, format: list[str], repository_name: str, scan: bool) -> None:
	"""
	This command creates metadata files in the specified directory.
	"""
	_metafile_update(directory=directory, read=False, format=format, repository_name=repository_name, scan=scan)


@metafile.command(short_help="Updates repository metadata files.", name="update")
@argument_directory
@option_format
@option_repository_name
@option_scan
def metafile_update(directory: Path, format: list[str], repository_name: str, scan: bool) -> None:
	"""
	This command updates metadata files in the specified directory.
	"""
	_metafile_update(directory=directory, read=True, format=format, repository_name=repository_name, scan=scan)


@metafile.command(short_help="Scan for opsi packages and update repository metadata files.", name="scan-packages")
@argument_directory
def metafile_scan_packages(directory: Path) -> None:
	"""
	This command scans for opsi packages in the specified directory and updates the metadata files.
	"""
	current_meta_files = list(directory.glob("packages.*"))
	if not current_meta_files:
		raise RuntimeError(f"No metadata files found in '{directory}'")

	_metafile_update(directory=directory, read=True, scan=True)


@metafile.command(short_help="Adds or updates a package in repository metadata files.", name="add-package")
@argument_directory
@click.argument("package", nargs=1, default=Path(), type=click.Path(file_okay=True, dir_okay=False, path_type=Path))
@click.option(
	"--num-allowed-versions",
	help="This limits the number of kept versions (allows keeping more than 1)",
	default=1,
)
@click.option("--compatibility", help="Compatible operating system and architecture in the form <os>-<arch>.", type=str, multiple=True)
@click.option(
	"--url",
	help="Explicitly use this URL in the package metadata instead of using the base and package path to create the URL.",
	type=str,
)
def add_package(directory: Path, package: Path, num_allowed_versions: int, compatibility: list[str], url: str | None) -> None:
	"""
	This command analyzes the specified opsi package and updates the meta-data file.
	"""
	current_meta_files = list(directory.glob("packages.*"))
	if not current_meta_files:
		raise RuntimeError(f"No metadata files found in '{directory}'")

	packages_metadata = RepoMetaPackageCollection()
	packages_metadata.read_metafile(current_meta_files[0])
	packages_metadata.add_package(
		directory,
		package,
		num_allowed_versions=num_allowed_versions,
		url=url,
		compatibility=[RepoMetaPackageCompatibility.from_string(c) for c in compatibility or []],
		add_callback=add_changelog_and_releasenote_url,
	)
	for meta_file in current_meta_files:
		packages_metadata.write_metafile(meta_file)


@metafile.command(short_help="Removes a package from repository metadata files.", name="remove-package")
@argument_directory
@click.argument("name", nargs=1, type=str)
@click.argument("version", nargs=1, type=str)
def remove_package(directory: Path, name: str, version: str) -> None:
	"""
	This command removes a package from repository metadata files.
	"""
	current_meta_files = list(directory.glob("packages.*"))
	if not current_meta_files:
		raise RuntimeError(f"No metadata files found in '{directory}'")

	packages_metadata = RepoMetaPackageCollection()
	packages_metadata.read_metafile(current_meta_files[0])

	packages_metadata.remove_package(name, version)
	for meta_file in current_meta_files:
		packages_metadata.write_metafile(meta_file)


class CustomPlugin(OPSICLIPlugin):
	name: str = "manage-repo"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
