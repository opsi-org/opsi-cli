"""
Support functions for installing packages.
"""

import os
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from opsicommon.client.opsiservice import ServiceClient
from opsicommon.logging import get_logger
from opsicommon.objects import BoolProductProperty, ProductProperty, UnicodeProductProperty
from opsicommon.package import OpsiPackage
from opsicommon.package.associated_files import md5sum

from OPSI.Util.File.Opsi import parseFilename
from OPSI.Util.Repository import getRepository  # type: ignore[import]
from opsicli import __version__
from opsicli.io import prompt

logger = get_logger("opsicli")


def sort_packages_by_dependency(opsi_packages: list[str]) -> list[Path]:
	"""
	Reorders a list of opsi packages based on their dependencies. Each package is placed after its dependencies in the list.
	"""
	dependencies = defaultdict(list)
	package_id_to_path = {}
	for pkg in opsi_packages:
		opsi_package = OpsiPackage(Path(pkg))
		package_id = opsi_package.product.id
		package_id_to_path[package_id] = Path(pkg)
		if opsi_package.package_dependencies:
			dependencies[package_id] = [dependency.package for dependency in opsi_package.package_dependencies]

	result = []
	visited = set()

	def visit(package_id: str) -> None:
		if package_id not in visited:
			visited.add(package_id)
			for dependency in dependencies[package_id]:
				if dependency not in package_id_to_path:
					raise ValueError(f"Dependency '{dependency}' not specified for package '{package_id}'.")
				visit(dependency)
			result.append(package_id_to_path[package_id])

	for package_id in package_id_to_path:
		visit(package_id)

	return result


def check_locked_products(service_client: ServiceClient, package_list: list[str], depot_list: list[str], force: bool) -> None:
	"""
	Check if the packages are locked on the depots. If they are locked, raise an error unless the force flag is set.
	"""
	locked_products = service_client.jsonrpc(
		"productOnDepot_getObjects", [["productId", "depotId"], {"productId": package_list, "depotId": depot_list, "locked": True}]
	)
	if locked_products and not force:
		error_message = f"Locked products found:\n\n{'ProductId':<30} {'DepotId':<30}\n" + "-" * 60 + "\n"
		for product in locked_products:
			error_message += f"{product.productId:<30} {product.depotId:<30}\n"
		error_message += "\nUse --force to install anyway."
		raise ValueError(error_message)


def get_local_path_from_repo_url(repo_local_url: str) -> str:
	"""
	Extracts and returns the local file system path from a depot repository local URL.
	"""
	if not repo_local_url.startswith("file://"):
		raise ValueError(f"Repository local URL '{repo_local_url}' is not supported. Must start with 'file://'.")
	depot_repository_path = repo_local_url[7:].rstrip("/")
	return depot_repository_path


def fix_custom_package_name(package_path: Path) -> str:
	"""
	Fixes the package name if it is a custom package.
	For example, the package name "testpackage_1.0-2~custom1.opsi" will be fixed to "testpackage_1.0-2.opsi".
	"""
	package_name = package_path.stem
	if "~" in package_name:
		fixed_name = package_name.split("~")[0] + ".opsi"
		logger.notice(f"Custom package detected: {package_name}. Fixed to: {fixed_name}")
		return fixed_name
	else:
		return f"{package_name}.opsi"


def update_product_properties(opsi_package: OpsiPackage) -> None:
	product_info = f"{opsi_package.product.id}_{opsi_package.product.productVersion}-{opsi_package.product.packageVersion}"
	product_properties: list[ProductProperty] = sorted(opsi_package.product_properties, key=lambda prop: prop.propertyId)
	for property in product_properties:
		property_info = f"Product: {product_info}" f"Property: {property.propertyId}\n" f"Enter default value"
		selected_values: str | int | float | list[Any] = ""
		if isinstance(property, BoolProductProperty):
			selected_values = str(
				prompt(
					f"{property_info}",
					default=str(property.defaultValues),
					choices=[str(choice) for choice in (property.possibleValues or [])],
					editable=property.editable,
				)
			).lower()
		if isinstance(property, UnicodeProductProperty):
			selected_values = prompt(
				f"{property_info}",
				default=str(property.defaultValues),
				choices=property.possibleValues,
				multi_value=property.multiValue,
				editable=property.editable,
			)

		print(selected_values)


def get_depot_connection(depot: Any) -> ServiceClient:
	"""
	Returns a connection to the depot.
	"""
	url = urlparse(depot.repositoryRemoteUrl)
	hostname = url.hostname
	if ":" in hostname:
		# IPv6 address
		hostname = f"[{hostname}]"
	connection = ServiceClient(
		address=f"https://{hostname}:{url.port or 4447}",
		username=depot.id,
		password=depot.opsiHostKey,
		user_agent=f"opsi-cli/{__version__}",
	)
	# TODO: client_cert_auth=True
	return connection


def get_checksum(package_path: Path) -> str:
	"""
	Checks the md5 file and returns the checksum if it exists, otherwise calculates the checksum.
	"""
	md5_file = package_path.with_suffix(".md5")
	if md5_file.exists():
		return md5_file.read_text()
	return md5sum(package_path)


def upload_to_repository(depot: Any, package_path: Path, package_name: str) -> None:
	"""
	Uploads a package to the depot's repository.
	"""
	logger.info("Uploading package %s to repository", package_path)
	try:
		depot_connection = get_depot_connection(depot)
		remote_package_file = depot.depotRepositoryPath + "/" + package_name
		remote_checksum = depot_connection.jsonrpc("depot_getMD5Sum", [[], {remote_package_file}])
		local_checksum = get_checksum(package_path)

		package_size = os.path.getsize(package_path)
		repository = getRepository(
			url=depot.repositoryRemoteUrl,
			username=depot.id,
			password=depot.opsiHostKey,
			maxBandwidth=(max(depot.maxBandwidth or 0, 0)) * 1000,
			application=f"opsi-cli/{__version__}",
			readTimeout=24 * 3600,
		)
		for repo_content in repository.content():
			print(repo_content)
			if repo_content["name"] == package_name:
				logger.info("Destination '%s' already exists on depot '%s'", package_name, depot.id)
				if repository.fileInfo(package_name)["size"] == package_size:
					logger.info("Size of source and destination matches on depot '%s'", depot.id)

					if local_checksum == remote_checksum:
						logger.notice("Checksum of source and destination matches on depot '%s'. No need to upload", depot.id)
						return

		repo_disk_space = depot_connection.jsonrpc("depot_getDiskSpaceUsage", [[], {depot.depotRepositoryPath}])
		if repo_disk_space["available"] < package_size:
			raise ValueError(
				f"Insufficient disk space on depot '{depot.id}' to upload package '{package_name}'. Needed: {package_size} bytes, available: {repo_disk_space['available']} bytes"
			)

		product_id = OpsiPackage(package_path).product.id
		packages_with_old_version = []
		for repo_content in repository.content():
			repo_file = parseFilename(repo_content["name"])
			if not repo_file:
				continue
			if repo_file.productId == product_id and repo_content["name"] != package_name:
				packages_with_old_version.append(repo_content["name"])

		logger.notice("Uploading package %s to depot %s started", package_name, depot.id)
		repository.upload(package_path, package_name)
		logger.notice("Uploading package %s to depot %s finished", package_name, depot.id)

		for old_package in packages_with_old_version:
			if old_package == package_name:
				continue
			logger.notice("Deleting old package %s from depot %s", old_package, depot.id)
			repository.delete(old_package)
			logger.notice("Deleting old package %s from depot %s finished", old_package, depot.id)

		logger.notice("Verifying upload")
		remote_checksum = depot_connection.jsonrpc("depot_getMD5Sum", [[], {remote_package_file}])
		if local_checksum != remote_checksum:
			raise ValueError(
				f"MD5sum of source '{local_checksum}' and destination '{remote_checksum}'" f"differ after upload to depot '{depot.id}'"
			)
		repo_disk_space = depot_connection.jsonrpc("depot_getDiskSpaceUsage", [[], {depot.depotRepositoryPath}])
		if repo_disk_space["usage"] >= 0.9:
			logger.warning("Warning: %d%% filesystem usage at repository on depot '%s'", int(100 * repo_disk_space["usage"]), depot.id)

		remote_package_md5sum_file = remote_package_file + ".md5"
		depot_connection.jsonrpc("depot_createMd5SumFile", [[], {remote_package_file, remote_package_md5sum_file}])
		remote_package_zsync_file = remote_package_file + ".zsync"
		depot_connection.jsonrpc("depot_createZsyncFile", [[], {remote_package_file, remote_package_zsync_file}])
	finally:
		repository.disconnect()


def install_package(depot: Any, package_path: Path) -> None:
	"""
	Installs a package on a depot.
	"""
	logger.info("Installing package %s on depot %s", package_path, depot.id)
	print(f"Installing package {package_path} on depot {depot.id}")
	print(depot.repositoryLocalUrl)
