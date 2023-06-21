"""
packages_metadata

Class to handle metadata of opsi packages
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import packaging.version as packver
import requests  # type: ignore
import zstandard
from msgspec import json, msgpack
from opsicommon.logging import get_logger
from opsicommon.objects import ProductDependency
from opsicommon.package import OpsiPackage
from opsicommon.system import lock_file

logger = get_logger("opsicli")
CHANGELOG_SERVER = "https://changelog.opsi.org"


class OperatingSystem(StrEnum):
	WINDOWS = "windows"
	MACOS = "macos"
	LINUX = "linux"


class Architecture(StrEnum):
	ALL = "all"
	X86 = "x86"
	X64 = "x64"
	ARM64 = "arm64"


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
class PackageCompatibility:
	os: OperatingSystem  # pylint: disable=invalid-name
	arch: Architecture

	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> PackageCompatibility:
		return PackageCompatibility(os=OperatingSystem(data["os"]), arch=Architecture(data["arch"]))

	@classmethod
	def from_string(cls, data: str) -> PackageCompatibility:
		os_arch = data.split("-")
		if len(os_arch) != 2:
			raise ValueError(f"Invalid compatibility string: {data!r} (<os>-<arch> needed)")
		return PackageCompatibility(os=OperatingSystem(os_arch[0]), arch=Architecture(os_arch[1]))


@dataclass
class RepositoryMetadata:
	name: str = "opsi package repository"


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
	compatibility: list[PackageCompatibility] | None = None

	changelog_url: str | None = None
	release_notes_url: str | None = None
	icon_url: str | None = None  # preparation for later
	zsync_url: str | None = None

	@property
	def version(self) -> str:
		return f"{self.product_version}-{self.package_version}"

	@classmethod
	def from_package_file(cls, package_file: Path, url: str, compatibility: list[PackageCompatibility] | None = None) -> PackageMetadata:
		logger.notice("Reading package file %s", package_file)
		data: dict[str, Any] = {"url": url, "size": package_file.stat().st_size}
		with open(package_file, "rb", buffering=0) as file_handle:
			# file_digest is python>=3.11 only
			data["md5_hash"] = hashlib.file_digest(file_handle, "md5").hexdigest()  # type: ignore
			data["sha256_hash"] = hashlib.file_digest(file_handle, "sha256").hexdigest()  # type: ignore
		if package_file.with_suffix(".opsi.zsync").exists():
			data["zsync_url"] = f"{url}.zsync"
		if compatibility:
			data["compatibility"] = compatibility

		opsi_package = OpsiPackage(package_file)
		data["product_id"] = opsi_package.product.id
		data["product_version"] = opsi_package.product.productVersion
		data["package_version"] = opsi_package.product.packageVersion
		data["description"] = opsi_package.product.description
		data["product_dependencies"] = [prod_dep_data(dep) for dep in opsi_package.product_dependencies]
		data["package_dependencies"] = [asdict(dep) for dep in opsi_package.package_dependencies]

		if url_exists(f"{CHANGELOG_SERVER}/OPSI_PACKAGE/{data['product_id']}/changelog.txt"):
			data["changelog_url"] = f"{CHANGELOG_SERVER}/OPSI_PACKAGE/{data['product_id']}/changelog.txt"
		if url_exists(f"{CHANGELOG_SERVER}/OPSI_PACKAGE/{data['product_id']}/release_notes.txt"):
			data["release_notes_url"] = f"{CHANGELOG_SERVER}/OPSI_PACKAGE/{data['product_id']}/release_notes.txt"

		return cls.from_dict(data)

	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> PackageMetadata:
		return PackageMetadata(**data)


@dataclass
class PackagesMetadataCollection:
	schema_version: str = "1.1"
	repository: RepositoryMetadata = field(default_factory=RepositoryMetadata)
	metadata_files: list[MetadataFile] = field(default_factory=list)
	packages: dict[str, dict[str, PackageMetadata]] = field(default_factory=dict)

	def scan_packages(self, directory: Path) -> None:
		logger.notice("Scanning opsi packages in %s", directory)
		for package in directory.rglob("*.opsi"):
			# Allow multiple versions for the same product in full scan
			self.add_package(directory, package, num_allowed_versions=0)
		logger.info("Finished scanning opsi packages")

	def limit_versions(self, name: str, num_allowed_versions: int = 1) -> None:
		versions = list(self.packages[name].keys())
		keep_versions = sorted(versions, key=packver.parse, reverse=True)[:num_allowed_versions]
		for version in versions:
			if version not in keep_versions:
				logger.debug("Removing %s %s as limit is %s", name, version, num_allowed_versions)
				del self.packages[name][version]

	def add_package(
		self,
		directory: Path,
		package_file: Path,
		*,
		num_allowed_versions: int = 1,
		compatibility: list[PackageCompatibility] | None = None,
		url: str | None = None,
	) -> None:
		if not url:
			url = str(package_file.relative_to(directory))
		url = str(url).replace("\\", "/")  # Cannot instantiate PosixPath on windows

		package = PackageMetadata.from_package_file(package_file=package_file, url=url, compatibility=compatibility)
		# Key only consists of only product id (otw11 revision 03.05.)
		if package.product_id not in self.packages or num_allowed_versions == 1:
			# if only one version is allowed, always delete previous version, EVEN IF IT HAS HIGHER VERSION
			self.packages[package.product_id] = {}
		self.packages[package.product_id][package.version] = package
		# num_allowed_versions = 0 means unlimited
		if num_allowed_versions and len(self.packages[package.product_id]) > num_allowed_versions:
			self.limit_versions(package.product_id, num_allowed_versions)

	def remove_package(self, name: str, version: str) -> None:
		if name in self.packages and version in self.packages[name]:
			del self.packages[name][version]
			if len(self.packages[name]) == 0:
				del self.packages[name]

	def read(self, path: Path) -> None:
		with open(path, mode="rb") as file:
			with lock_file(file):
				data: dict[str, Any] = {}
				bdata = file.read()
				if bdata:
					head = bdata[0:4].hex()
					if head == "28b52ffd":
						decompressor = zstandard.ZstdDecompressor()
						bdata = decompressor.decompress(bdata)

					if bdata.startswith(b"{"):
						data = json.decode(bdata)
					else:
						data = msgpack.decode(bdata)

				self.schema_version = data.get("schema_version", self.schema_version)
				self.repository = RepositoryMetadata(**data.get("repository", {}))
				self.metadata_files = [MetadataFile(entry.get("type"), entry.get("urls")) for entry in data.get("metadata_files", [])]
				self.packages = {}
				for name, product in data.get("packages", {}).items():
					if name not in self.packages:
						self.packages[name] = {}
					self.packages[name] = {version: PackageMetadata.from_dict(data) for version, data in product.items()}

	def write(self, path: Path) -> None:
		encoding = "json"
		compression: str | None = None
		if ".msgpack" in path.suffixes:
			encoding = "msgpack"
		if ".zstd" in path.suffixes:
			compression = "zstd"

		logger.notice("Writing result to %s (encoding=%s, compression=%s)", path, encoding, compression)
		result = {
			"schema_version": self.schema_version,
			"repository": asdict(self.repository),
			"metadata_files": [asdict(metadata_file) for metadata_file in self.metadata_files],
		}
		packages_dict: dict[str, dict[str, Any]] = {}
		for name, product in self.packages.items():
			if name not in result:
				packages_dict[name] = {}
			packages_dict[name] = {version: asdict(package) for version, package in product.items()}
		result["packages"] = packages_dict

		data = msgpack.encode(result) if encoding == "msgpack" else json.encode(result)
		if compression:
			if compression != "zstd":
				raise ValueError(f"Invalid compression: {compression}")
			compressor = zstandard.ZstdCompressor()
			data = compressor.compress(data)

		if not path.exists():
			path.touch()  # Need to create file before it can be opened with r+
		with open(path, "rb+") as file:
			with lock_file(file, exclusive=True):
				file.seek(0)
				file.truncate()
				file.write(data)
