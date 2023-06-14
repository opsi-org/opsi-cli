"""
packages_metadata

Class to handle metadata of opsi packages
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import packaging.version as packver
import requests  # type: ignore
from opsicommon.logging import get_logger
from opsicommon.objects import ProductDependency
from opsicommon.package import OpsiPackage
from opsicommon.system import lock_file

logger = get_logger("opsicli")
CHANGELOG_SERVER = "https://changelog.opsi.org"


@dataclass
class MetadataFile:
	type: str
	urls: list[str]


def prod_dep_data(dep: ProductDependency) -> dict[str, str | None]:
	wanted_keys = (
		"requiredProductVersion",
		"requiredPackageVersion",
		"requiredAction",
		"requiredInstallationStatus",
		"requirementType",
		"productAction",
		"requiredProductId",
	)
	return {key: value for key, value in dep.to_hash().items() if key in wanted_keys}


def url_exists(url: str) -> bool:
	result = requests.head(url, timeout=(5, 5))
	if result.status_code >= 200 and result.status_code < 300:
		return True
	return False


@dataclass
class PackageMetadata:  # pylint: disable=too-many-instance-attributes
	url: str
	size: int
	md5_hash: str
	sha256_hash: str

	product_id: str
	product_version: str
	package_version: str
	product_dependencies: list[dict[str, str | None]]
	package_dependencies: list[dict[str, str]]
	description: str | None = None
	compatibility: list[str] | None = None

	changelog_url: str | None = None
	release_notes_url: str | None = None
	icon_url: str | None = None  # preparation for later
	zsync_url: str | None = None

	def __init__(
		self,
		archive: Path | None = None,
		data: dict[str, Any] | None = None,
		relative_path: Path | None = None,
		compatibility: str | None = None,
	) -> None:
		if archive and data:
			raise ValueError("Cannot specify both archive and data")
		if archive:
			self.from_archive(archive, relative_path=relative_path, compatibility=compatibility)
			return
		if data:
			self.from_dict(data)
			return
		raise ValueError("Must specify either archive or data")

	@property
	def version(self) -> str:
		return f"{self.product_version}-{self.package_version}"

	def from_archive(self, archive: Path, relative_path: Path | None = None, compatibility: str | None = None) -> None:
		logger.notice("Reading package archive %s", archive)
		if not relative_path:
			relative_path = archive.relative_to(Path.cwd())
		self.url = str(relative_path).replace("\\", "/")  # Cannot instantiate PosixPath on windows
		self.size = archive.stat().st_size
		with open(archive, "rb", buffering=0) as file_handle:
			# file_digest is python>=3.11 only
			self.md5_hash = hashlib.file_digest(file_handle, "md5").hexdigest()  # type: ignore
			self.sha256_hash = hashlib.file_digest(file_handle, "sha256").hexdigest()  # type: ignore
		if archive.with_suffix(".opsi.zsync").exists():
			self.zsync_url = str(relative_path.with_suffix(".opsi.zsync")).replace("\\", "/")
		if compatibility:
			self.compatibility = compatibility.split(",")

		opsi_package = OpsiPackage(archive)
		self.product_id = opsi_package.product.id
		self.product_version = opsi_package.product.productVersion
		self.package_version = opsi_package.product.packageVersion
		self.description = opsi_package.product.description
		self.product_dependencies = [prod_dep_data(dep) for dep in opsi_package.product_dependencies]
		self.package_dependencies = [asdict(dep) for dep in opsi_package.package_dependencies]

		if url_exists(f"{CHANGELOG_SERVER}/OPSI_PACKAGE/{self.product_id}/changelog.txt"):
			self.changelog_url = f"{CHANGELOG_SERVER}/OPSI_PACKAGE/{self.product_id}/changelog.txt"
		if url_exists(f"{CHANGELOG_SERVER}/OPSI_PACKAGE/{self.product_id}/release_notes.txt"):
			self.release_notes_url = f"{CHANGELOG_SERVER}/OPSI_PACKAGE/{self.product_id}/release_notes.txt"

	def from_dict(self, data: dict[str, Any]) -> None:
		if not (
			isinstance(data["url"], str)
			and isinstance(data["size"], int)
			and isinstance(data["md5_hash"], str)
			and isinstance(data["sha256_hash"], str)
			and isinstance(data["product_id"], str)
			and isinstance(data["product_version"], str)
			and isinstance(data["package_version"], str)
		):
			raise ValueError(f"Invalid data to build PackageMetadata from: {data}")
		self.url = data["url"]
		self.size = data["size"]
		self.md5_hash = data["md5_hash"]
		self.sha256_hash = data["sha256_hash"]
		self.product_id = data["product_id"]
		self.product_version = data["product_version"]
		self.package_version = data["package_version"]
		self.product_dependencies = data.get("product_dependencies", [])
		self.package_dependencies = data.get("package_dependencies", [])
		self.description = data.get("description")
		self.changelog_url = data.get("changelog_url")
		self.release_notes_url = data.get("release_notes_url")
		self.icon_url = data.get("icon_url")
		self.zsync_url = data.get("zsync_url")
		self.compatibility = data.get("compatibility")


class PackagesMetadataCollection:
	def __init__(self, path: Path | None = None) -> None:
		self.schema_version: str = "1.1"
		self.repository: dict[str, str] = {}
		self.metadata_files: list[MetadataFile] = []
		self.packages: dict[str, dict[str, PackageMetadata]] = {}
		if path and path.exists():
			with open(path, mode="r", encoding="utf-8") as infile:
				data = json.load(infile)
				self.schema_version = data.get("schema_version")
				self.repository = data.get("repository")
				self.metadata_files = [MetadataFile(entry.get("type"), entry.get("urls")) for entry in data.get("metadata_files")]
				self.packages = {}
				for name, product in data.get("packages", {}).items():
					if name not in self.packages:
						self.packages[name] = {}
					self.packages[name] = {version: PackageMetadata(data=package) for version, package in product.items()}

	def collect(self, path: Path, repo_name: str) -> None:
		self.repository = {"name": repo_name}
		logger.notice("Starting to collect metadata from %s", path)
		for archive in path.rglob("*.opsi"):
			# allow multiple versions for the same product in full scan
			self.add_package(archive, num_allowed_versions=0, relative_path=archive.relative_to(path.parent))
		logger.info("Finished collecting metadata")

	def limit_versions(self, name: str, num_allowed_versions: int = 1) -> None:
		versions = list(self.packages[name].keys())
		keep_versions = sorted(versions, key=packver.parse, reverse=True)[:num_allowed_versions]
		for version in versions:
			if version not in keep_versions:
				logger.debug("Removing %s %s as limit is %s", name, version, num_allowed_versions)
				del self.packages[name][version]

	def add_package(
		self, archive: Path, num_allowed_versions: int = 1, relative_path: Path | None = None, compatibility: str | None = None
	) -> None:
		package = PackageMetadata(archive=archive, relative_path=relative_path, compatibility=compatibility)
		# Key only consists of only product id (otw11 revision 03.05.)
		if package.product_id not in self.packages or num_allowed_versions == 1:
			# if only one version is allowed, always delete previous version, EVEN IF IT HAS HIGHER VERSION
			self.packages[package.product_id] = {}
		self.packages[package.product_id][package.version] = package
		# num_allowed_versions = 0 means unlimited
		if num_allowed_versions and len(self.packages[package.product_id]) > num_allowed_versions:
			self.limit_versions(package.product_id, num_allowed_versions)

	def write(self, path: Path) -> None:
		logger.notice("Writing result to %s", path)
		result = {
			"schema_version": self.schema_version,
			"repository": self.repository,
			"metadata_files": [asdict(metadata_file) for metadata_file in self.metadata_files],
		}
		packages_dict: dict[str, dict[str, Any]] = {}
		for name, product in self.packages.items():
			if name not in result:
				packages_dict[name] = {}
			packages_dict[name] = {version: asdict(package) for version, package in product.items()}
		result["packages"] = packages_dict

		if not path.exists():
			path.touch()  # Need to create file before it can be opened with r+
		with open(path, "r+", encoding="utf-8") as file:
			with lock_file(file):
				file.seek(0)
				file.truncate()
				file.write(json.dumps(result))
