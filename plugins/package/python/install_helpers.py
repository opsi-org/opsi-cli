"""
Support functions for installing packages.
"""

import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from opsicommon.client.opsiservice import ServiceClient
from opsicommon.logging import get_logger
from opsicommon.objects import BoolProductProperty, OpsiConfigserver, OpsiDepotserver, ProductProperty, UnicodeProductProperty
from opsicommon.package import OpsiPackage
from opsicommon.package.associated_files import md5sum
from rich.progress import Progress

from OPSI.Util.File.Opsi import parseFilename  # type: ignore[import]
from OPSI.Util.Repository import WebDAVRepository, getRepository  # type: ignore[import]
from opsicli import __version__
from opsicli.io import get_console, prompt

logger = get_logger("opsicli")
DEPOT_REPOSITORY_PATH = "/var/lib/opsi/repository"


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


def check_locked_products(
	service_client: ServiceClient, opsi_packages: list[Path], depot_objects: list[OpsiConfigserver | OpsiDepotserver], force: bool
) -> None:
	"""
	Check if the packages are locked on the depots. If they are locked, raise an error unless the force flag is set.
	"""
	package_list = [OpsiPackage(pkg).product.id for pkg in opsi_packages]
	depot_id_list = [depot.id for depot in depot_objects]
	locked_products = service_client.jsonrpc(
		"productOnDepot_getObjects", [["productId", "depotId"], {"productId": package_list, "depotId": depot_id_list, "locked": True}]
	)
	if locked_products and not force:
		error_message = f"Locked products found:\n\n{'ProductId':<30} {'DepotId':<30}\n" + "-" * 60 + "\n"
		for product in locked_products:
			error_message += f"{product.productId:<30} {product.depotId:<30}\n"
		error_message += "\nUse --force to install anyway."
		raise ValueError(error_message)


def fix_custom_package_name(package_path: Path) -> str:
	"""
	Fixes the package name if it is a custom package.
	For example, the package name "testpackage_1.0-2~custom.opsi" will be fixed to "testpackage_1.0-2.opsi".
	"""
	package_name = package_path.name
	if "~" in package_name:
		fixed_name = package_name.split("~")[0] + ".opsi"
		logger.notice("Custom package detected: %s. Fixed to: %s", package_name, fixed_name)
		return fixed_name
	return package_name


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


def get_checksum(package_path: Path) -> str:
	"""
	Checks the md5 file and returns the content if it exists, otherwise calculates the checksum.
	"""
	md5_file = package_path.with_suffix(".md5")
	if md5_file.exists():
		return md5_file.read_text()
	return md5sum(package_path)


def check_pkg_existence_and_integrity(
	depot_connection: ServiceClient,
	repository: WebDAVRepository,
	dest_package_name: str,
	package_size: int,
	local_checksum: str,
) -> bool:
	if not any(repo_content["name"] == dest_package_name for repo_content in repository.content()):
		return False

	repo_file_info = repository.fileInfo(dest_package_name)
	remote_checksum = depot_connection.jsonrpc("depot_getMD5Sum", [DEPOT_REPOSITORY_PATH + "/" + dest_package_name])

	if repo_file_info["size"] != package_size:
		logger.info("Size of source and destination differs.")
		return False

	if local_checksum != remote_checksum:
		logger.info("Checksum of source and destination differs.")
		return False

	logger.notice("Package '%s' already exists in the repository with matching size and checksum. Skipping upload.", dest_package_name)
	get_console().print(
		f"Package '{dest_package_name}' already exists in the repository with matching size and checksum. Skipping upload.\n"
	)
	return True


def check_disk_space(depot_connection: ServiceClient, depot_id: str, package_size: int) -> None:
	available_space = depot_connection.jsonrpc("depot_getDiskSpaceUsage", [DEPOT_REPOSITORY_PATH])["available"]
	if available_space < package_size:
		logger.error(
			"Insufficient disk space on depot '%s'. Needed: %d bytes, available: %d bytes", depot_id, package_size, available_space
		)
		raise ValueError(f"Insufficient disk space on depot '{depot_id}'. Needed: {package_size} bytes, available: {available_space} bytes")


def cleanup_old_packages(repository: WebDAVRepository, source_product_id: str, dest_package_name: str) -> None:
	for repo_content in repository.content():
		repo_file = parseFilename(repo_content["name"])
		if repo_file and repo_file.productId == source_product_id and repo_content["name"] != dest_package_name:
			logger.notice("Deleting old package %s from depot", repo_content["name"])
			repository.delete(repo_content["name"])


def validate_upload_and_check_disk_space(
	depot_connection: ServiceClient, depot_id: str, local_checksum: str, remote_package_file: str
) -> None:
	logger.info("Validating upload and checking disk space")
	remote_checksum = depot_connection.jsonrpc("depot_getMD5Sum", [remote_package_file])
	if local_checksum != remote_checksum:
		logger.error("MD5sum mismatch: local='%s', remote='%s' after upload to depot '%s'", local_checksum, remote_checksum, depot_id)
		raise ValueError(f"MD5sum mismatch: local='{local_checksum}', remote='{remote_checksum}' after upload to depot '{depot_id}'")

	usage = depot_connection.jsonrpc("depot_getDiskSpaceUsage", [DEPOT_REPOSITORY_PATH])["usage"]
	if usage >= 0.9:
		logger.warning("Filesystem usage at %d%% on depot '%s'", int(usage * 100), depot_id)


def create_remote_md5_and_zsync_files(depot_connection: ServiceClient, remote_package_file: str) -> None:
	logger.info("Creating MD5 and zsync files on repository for package '%s'", remote_package_file)
	remote_package_md5sum_file = remote_package_file + ".md5"
	depot_connection.jsonrpc("depot_createMd5SumFile", [remote_package_file, remote_package_md5sum_file])
	remote_package_zsync_file = remote_package_file + ".zsync"
	depot_connection.jsonrpc("depot_createZsyncFile", [remote_package_file, remote_package_zsync_file])


def upload_to_repository(
	depot_connection: ServiceClient, depot: OpsiConfigserver | OpsiDepotserver, source_package: Path, dest_package_name: str
) -> None:
	"""
	Uploads a package to the depot's repository.
	"""
	logger.notice("Uploading package '%s' to the repository on depot '%s'.", dest_package_name, depot.id)
	package_size = os.path.getsize(source_package)
	local_checksum = get_checksum(source_package)
	remote_package_file = DEPOT_REPOSITORY_PATH + "/" + dest_package_name
	try:
		repository = getRepository(
			url=depot.repositoryRemoteUrl,
			username=depot.id,
			password=depot.opsiHostKey,
			maxBandwidth=(max(depot.maxBandwidth or 0, 0)) * 1000,
			application=f"opsi-cli/{__version__}",
			readTimeout=24 * 3600,
		)
		if check_pkg_existence_and_integrity(depot_connection, repository, dest_package_name, package_size, local_checksum):
			return
		check_disk_space(depot_connection, depot.id, package_size)

		logger.notice("Starting upload of package %s to depot %s", dest_package_name, depot.id)
		with Progress() as progress:
			task = progress.add_task(f"Uploading '{dest_package_name}' to depot '{depot.id}'...", total=package_size)
			repository.upload(str(source_package), dest_package_name)
			progress.update(task, completed=package_size)
		logger.notice("Finished upload of package %s to depot %s", dest_package_name, depot.id)

		cleanup_old_packages(repository, OpsiPackage(source_package).product.id, dest_package_name)
		validate_upload_and_check_disk_space(depot_connection, depot.id, local_checksum, remote_package_file)
		create_remote_md5_and_zsync_files(depot_connection, remote_package_file)
	finally:
		if repository:
			repository.disconnect()


def get_property_default_values(opsi_package: OpsiPackage) -> dict:
	property_default_values = {}
	for product_property in opsi_package.product_properties:
		property_default_values[product_property.propertyId] = product_property.defaultValues or []
	return property_default_values


def update_property_default_values(service_client: ServiceClient, depot_id: str, product_id: str, property_default_values: dict) -> None:
	product_property_states = service_client.jsonrpc(
		"productPropertyState_getObjects",
		[[], {"productId": product_id, "objectId": depot_id}],
	)
	for product_property_state in product_property_states:
		if product_property_state.propertyId in property_default_values:
			property_default_values[product_property_state.propertyId] = product_property_state.values or []


def install_package(
	depot: OpsiConfigserver | OpsiDepotserver,
	depot_connection: ServiceClient,
	package_path: Path,
	package_name: str,
	update_properties: bool,
	service_client: ServiceClient,
) -> None:
	"""
	Installs a package on a depot.
	"""
	logger.info("Installing package %s on depot %s", package_path, depot.id)
	print(f"Installing package {package_path} on depot {depot.id}")
	remote_package_file = DEPOT_REPOSITORY_PATH + "/" + package_name
	opsi_package = OpsiPackage(package_path)
	product_id = opsi_package.product.id

	property_default_values = get_property_default_values(opsi_package)
	if not update_properties:
		update_property_default_values(service_client, depot.id, product_id, property_default_values)

	installation_params = {"force": True, "propertyDefaultValues": property_default_values}

	# depot_connection = get_depot_connection(depot)
	depot_connection.jsonrpc("depot_installPackage", [[], {remote_package_file, installation_params}])
	# TODO: set_product_cache_outdated
	logger.notice("Installation of package %s on depot %s successful", remote_package_file, depot.id)
