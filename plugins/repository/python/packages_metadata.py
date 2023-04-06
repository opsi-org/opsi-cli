"""
packages_metadata

Class to handle metadata of opsi packages
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from opsicommon.logging import get_logger
from opsicommon.package import OpsiPackage

logger = get_logger("opsicli")


@dataclass
class MetadataFile:
	type: str
	urls: list[str]


@dataclass
class PackageMetadata:  # pylint: disable=too-many-instance-attributes
	url: str
	size: int
	md5_hash: str
	sha256_hash: str

	product_id: str
	product_version: str
	package_version: str
	product_dependencies: list[dict[str, str]]
	package_dependencies: list[dict[str, str]]
	description: str | None = None

	changelog_url: str | None = None
	release_notes_url: str | None = None
	icon_url: str | None = None
	zsync_url: str | None = None

	def __init__(self, archive: Path) -> None:
		self.from_archive(archive)

	def from_archive(self, archive: Path) -> None:
		logger.notice("Reading package archive %s to extract meta data", archive)
		self.url = str(archive)  # TODO: relative to base_dir!
		self.size = archive.stat().st_size
		with open(archive, "rb", buffering=0) as file_handle:
			# file_digest is python>=3.11 only
			self.md5_hash = hashlib.file_digest(file_handle, "md5").hexdigest()  # type: ignore
			self.sha256_hash = hashlib.file_digest(file_handle, "sha256").hexdigest()  # type: ignore
		if archive.with_suffix(".opsi.zsync").exists():
			self.md5_hash = str(archive.with_suffix(".opsi.zsync"))
		# TODO: changelog_url - check if exists? or check once beforehand which are available -> crawler needed?
		# TODO: release_notes_url - check if exists? or check once beforehand which are available -> crawler needed?
		# TODO: icon_url - ?

		opsi_package = OpsiPackage(archive)
		self.product_id = opsi_package.product.id
		self.product_version = opsi_package.product.productVersion
		self.package_version = opsi_package.product.packageVersion
		self.description = opsi_package.product.description
		self.product_dependencies = [dep.to_hash() for dep in opsi_package.product_dependencies]
		self.package_dependencies = [asdict(dep) for dep in opsi_package.package_dependencies]


class PackagesMetadataCollection:
	def __init__(self, repo_name: str) -> None:
		self.schema_version: str = "1.1"
		self.repository: dict[str, str] = {"name": repo_name}
		self.metadata_files: list[MetadataFile] = []
		self.packages: dict[str, PackageMetadata] = {}

	def collect(self, path: Path) -> None:
		for archive in path.rglob("*.opsi"):
			package = PackageMetadata(archive)
			self.packages[f"{package.product_id};{package.product_version};{package.package_version}"] = package

	def write(self, path: Path) -> None:
		result = {
			"schema_version": self.schema_version,
			"repository": self.repository,
			"metadata_files": [asdict(metadata_file) for metadata_file in self.metadata_files],
			"packages": {name: asdict(package) for name, package in self.packages.items()},
		}
		path.write_text(json.dumps(result))
