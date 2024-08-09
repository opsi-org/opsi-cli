"""
Support functions for installing packages.
"""

import os
from pathlib import Path
from typing import Any

from opsicommon.client.opsiservice import ServiceClient
from opsicommon.logging import get_logger
from opsicommon.objects import BoolProductProperty, OpsiConfigserver, OpsiDepotserver, ProductProperty
from opsicommon.package import OpsiPackage
from opsicommon.package.associated_files import md5sum
from rich.progress import Progress

from OPSI.Util.File.Opsi import parseFilename  # type: ignore[import]
from OPSI.Util.Repository import WebDAVRepository, getRepository  # type: ignore[import]
from opsicli import __version__
from opsicli.config import config
from opsicli.io import get_console, prompt

logger = get_logger("opsicli")
DEPOT_REPOSITORY_PATH = "/var/lib/opsi/repository"


def get_depot_objects(service_client: ServiceClient, depots: str) -> list[OpsiConfigserver | OpsiDepotserver]:
	"""
	This function makes a JSON-RPC call to the "host_getObjects" with the depots filter.
	"""
	depot_filter: dict[str, str | list[str]] = (
		{"type": "OpsiDepotserver"}
		if depots == "all"
		else {"id": [depot.strip() for depot in depots.split(",")]}
		if depots
		else {"type": "OpsiConfigserver"}
	)
	return service_client.jsonrpc("host_getObjects", [[], depot_filter])


def map_opsipackages_to_paths(packages: list[str]) -> dict[Path, OpsiPackage]:
	"""
	Returns a dictionary with the package path to the OpsiPackage object.
	"""
	path_to_opsipackage_dict = {}
	for pkg in packages:
		opsi_package = OpsiPackage(Path(pkg))
		path_to_opsipackage_dict[Path(pkg)] = opsi_package
	return path_to_opsipackage_dict


def sort_packages_by_dependency(path_to_opsipackage_dict: dict[Path, OpsiPackage]) -> list[Path]:
	"""
	Reorders a list of opsi packages based on their dependencies. Each package is placed after its dependencies in the list.
	"""
	product_id_to_path = {opsi_package.product.id: path for path, opsi_package in path_to_opsipackage_dict.items()}
	result = []
	visited = set()

	def visit(product_id: str) -> None:
		if product_id not in visited:
			visited.add(product_id)
			opsi_package = path_to_opsipackage_dict[product_id_to_path[product_id]]
			dependencies = (
				[dependency.package for dependency in opsi_package.package_dependencies] if opsi_package.package_dependencies else []
			)
			for dependency in dependencies:
				if dependency not in product_id_to_path:
					raise ValueError(f"Dependency '{dependency}' for package '{product_id}' is not specified.")
				visit(dependency)
			result.append(product_id_to_path[product_id])

	for product_id in product_id_to_path:
		visit(product_id)
	return result


def check_locked_products(
	service_client: ServiceClient,
	depot_objects: list[OpsiConfigserver | OpsiDepotserver],
	path_to_opsipackage_dict: dict[Path, OpsiPackage],
) -> None:
	"""
	Checks if the packages are locked on the depots and raises an error if any are found.
	"""
	product_list = [opsi_package.product.id for opsi_package in path_to_opsipackage_dict.values()]
	depot_id_list = [depot.id for depot in depot_objects]
	locked_products = service_client.jsonrpc(
		"productOnDepot_getObjects", [["productId", "depotId"], {"productId": product_list, "depotId": depot_id_list, "locked": True}]
	)
	if locked_products:
		logger.error("Locked products found: %s", locked_products)
		error_message = f"Locked products found:\n\n{'ProductId':<30} {'DepotId':<30}\n" + "-" * 60 + "\n"
		for product in locked_products:
			error_message += f"{product.productId:<30} {product.depotId:<30}\n"
		error_message += "\nUse --force to install anyway."
		raise ValueError(error_message)


def get_hint(product_property: ProductProperty) -> str:
	"""
	Returns a hint for the product property.
	"""
	if product_property.editable:
		return (
			"Choose multiple options, type 'done' to finish, or enter a new value"
			if product_property.multiValue
			else "Choose one option or enter a new value"
		)
	return "Choose multiple options or type 'done' to finish" if product_property.multiValue else ""


def get_choices(product_property: ProductProperty) -> list[Any] | None:
	"""
	Returns the possible values for the product property.
	"""
	if isinstance(product_property, BoolProductProperty):
		return [str(choice) for choice in (product_property.possibleValues or [])]
	return product_property.possibleValues


def prompt_for_values(product_property: ProductProperty, prompt_text: str) -> list[Any]:
	"""
	Prompts the user for the product property values.
	"""
	selected_values: list[str | int | float] = []
	if product_property.multiValue:
		while True:
			choice = prompt(
				prompt_text,
				default=str(product_property.defaultValues),
				choices=None if product_property.editable else (get_choices(product_property) or []) + ["done"],
			)
			if choice in ["done", ""]:
				break
			if choice not in selected_values:
				selected_values.append(choice)
	else:
		choice = prompt(
			prompt_text,
			default=str(product_property.defaultValues),
			choices=None if product_property.editable else get_choices(product_property),
		)
		selected_values.append(choice)
	return selected_values


def update_product_properties(path_to_opsipackage_dict: dict[Path, OpsiPackage]) -> None:
	"""
	Updates the default values and possible values of the product properties based on the user input.
	"""
	for opsi_package in path_to_opsipackage_dict.values():
		product_info = f"{opsi_package.product.id}_{opsi_package.product.productVersion}-{opsi_package.product.packageVersion}"
		product_properties = sorted(opsi_package.product_properties, key=lambda prop: prop.propertyId)

		for product_property in product_properties:
			property_info = (
				f"\n"
				f" {'Product':<20}  {product_info:<25} \n"
				f" {'Property ID':<20}  \033[36m{product_property.propertyId:<25}\033[0m \n"
				f" {'Description':<20}  {product_property.description:<25} \n"
				f"\n"
				f"Enter default value:"
			)

			hint = get_hint(product_property)
			prompt_text = f"{property_info} [dim]{hint}[/dim]" + (
				f" [bold bright_magenta]{product_property.possibleValues}" if product_property.editable else ""
			)

			selected_values = prompt_for_values(product_property, prompt_text)

			if product_property.editable:
				new_possible_values = set(product_property.getPossibleValues() or [])
				new_possible_values.update(selected_values)
				product_property.setPossibleValues(list(new_possible_values))

			product_property.setDefaultValues(selected_values)


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


def get_checksum(package_path: Path) -> str:
	"""
	Checks the md5 file and returns the content if it exists, otherwise calculates the checksum.
	"""
	md5_file = package_path.with_suffix(".md5")
	if md5_file.exists():
		logger.info("MD5 file found for package %s", package_path)
		return md5_file.read_text()
	logger.info("Calculating MD5 checksum for package %s", package_path)
	return md5sum(package_path)


def check_pkg_existence_and_integrity(
	depot_connection: ServiceClient,
	repository: WebDAVRepository,
	dest_package_name: str,
	package_size: int,
	local_checksum: str,
) -> bool:
	"""
	Check if the package already exists in the repository and has the same size and checksum. If it does, skip the upload.
	"""
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
	get_console().print(f"Package '{dest_package_name}' already exists in the repository with matching size and checksum. Skipping upload.")
	return True


def check_disk_space(depot_connection: ServiceClient, depot_id: str, package_size: int) -> None:
	"""
	Check if there is enough disk space on the depot for the package.
	"""
	available_space = depot_connection.jsonrpc("depot_getDiskSpaceUsage", [DEPOT_REPOSITORY_PATH])["available"]
	if available_space < package_size:
		logger.error(
			"Insufficient disk space on depot '%s'. Needed: %d bytes, available: %d bytes", depot_id, package_size, available_space
		)
		raise ValueError(f"Insufficient disk space on depot '{depot_id}'. Needed: {package_size} bytes, available: {available_space} bytes")


def cleanup_old_packages(repository: WebDAVRepository, source_product_id: str, dest_package_name: str) -> None:
	"""
	Deletes old packages from the depot repository.
	"""
	for repo_content in repository.content():
		repo_file = parseFilename(repo_content["name"])
		if repo_file and repo_file.productId == source_product_id and repo_content["name"] != dest_package_name:
			logger.notice("Deleting old package %s from depot", repo_content["name"])
			repository.delete(repo_content["name"])


def validate_upload_and_check_disk_space(
	depot_connection: ServiceClient, depot_id: str, local_checksum: str, remote_package_file: str
) -> None:
	"""
	Validates the upload by comparing the checksums and also checks the disk space on the depot. If the disk space usage is above 90%, a warning is logged.
	"""
	logger.info("Validating upload and checking disk space")
	remote_checksum = depot_connection.jsonrpc("depot_getMD5Sum", [remote_package_file])
	if local_checksum != remote_checksum:
		logger.error("MD5sum mismatch: local='%s', remote='%s' after upload to depot '%s'", local_checksum, remote_checksum, depot_id)
		raise ValueError(f"MD5sum mismatch: local='{local_checksum}', remote='{remote_checksum}' after upload to depot '{depot_id}'")

	usage = depot_connection.jsonrpc("depot_getDiskSpaceUsage", [DEPOT_REPOSITORY_PATH])["usage"]
	if usage >= 0.9:
		logger.warning("Filesystem usage at %d%% on depot '%s'", int(usage * 100), depot_id)


def create_remote_md5_and_zsync_files(depot_connection: ServiceClient, remote_package_file: str) -> None:
	"""
	Creates the MD5 and zsync files on the depot repository.
	"""
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
	logger.info("Uploading package '%s' to the repository on depot '%s'.", dest_package_name, depot.id)
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


def get_property_default_values(
	service_client: ServiceClient,
	depot_id: str,
	opsi_package: OpsiPackage,
	update_properties: bool,
) -> dict[str, list[Any]]:
	"""
	Get the default values for the product properties.

	If `update_properties` is True and the configuration is interactive,
	retrieve default values from the Opsi package. Otherwise, fetch values
	from `productPropertyState_getObjects`.
	"""
	product_id = opsi_package.product.id
	property_default_values = {}

	if update_properties and config.interactive:
		property_default_values = {
			product_property.propertyId: product_property.defaultValues or [] for product_property in opsi_package.product_properties
		}
	else:
		product_property_states = service_client.jsonrpc(
			"productPropertyState_getObjects",
			[[], {"productId": product_id, "objectId": depot_id}],
		)
		property_default_values = {prod_prop_state.propertyId: prod_prop_state.values or [] for prod_prop_state in product_property_states}

	return property_default_values


def install_package(
	depot_connection: ServiceClient,
	depot: OpsiConfigserver | OpsiDepotserver,
	dest_package_name: str,
	force: bool,
	property_default_values: dict[str, list[Any]],
) -> None:
	"""
	Installs a package on a depot.
	"""
	logger.info("Installing package %s on depot %s", dest_package_name, depot.id)
	remote_package_file = DEPOT_REPOSITORY_PATH + "/" + dest_package_name
	installation_params = [remote_package_file, str(force), property_default_values]
	logger.notice("Starting installation of package %s to depot %s", dest_package_name, depot.id)
	with Progress() as progress:
		task = progress.add_task(f"Installing '{dest_package_name}' to depot '{depot.id}'...\n", total=100)
		depot_connection.jsonrpc("depot_installPackage", installation_params)
		progress.update(task, completed=100)
	logger.notice("Finished installation of package %s to depot %s", dest_package_name, depot.id)
