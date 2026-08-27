# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
Support functions for installing packages.
"""

import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from opsi.archive import extract_archive
from opsi.logging import get_logger
from opsi.opsi.package import OpsiPackage, create_package_md5_file, create_package_zsync_file
from opsi.opsi.service.client import ServiceClient
from opsi.opsi.service.model.object import (
	BoolProductProperty,
	OpsiDepotserver,
	Product,
	ProductDependency,
	ProductOnClient,
	ProductOnDepot,
	ProductProperty,
	opsi_timestamp,
)
from opsi.opsi.service.model.type import to_host_id_list

from opsicli.io import OutputType, console_print, get_progress, get_separated_entries, prompt, write_output
from opsicli.opsiservice import get_depot_connection
from opsicli.utils import ProgressCallbackAdapter, download

from .metadata import COMMAND_METADATA
from .package_progress import PackageProgressListener

DEPOT_REPOSITORY_PATH = "/var/lib/opsi/repository"


logger = get_logger("opsicli")


@lru_cache(maxsize=100)
def get_depot_objects(service_client: ServiceClient, depots: str) -> list[OpsiDepotserver]:
	"""
	This function makes a JSON-RPC call to the "host_getObjects" with the depots filter.
	"""
	depot_filter: dict[str, str | list[str]] = (
		{"type": "OpsiDepotserver"}
		if depots == "all"
		else {"id": to_host_id_list([depot.lower() for depot in get_separated_entries(depots)])}
		if depots
		else {"type": "OpsiConfigserver"}
	)
	return service_client.jsonrpc("host_getObjects", [[], depot_filter])


@lru_cache(maxsize=100)
def get_product_on_depot_objects(service_client: ServiceClient, depot_list: tuple) -> list[ProductOnDepot]:
	"""
	This function makes a JSON-RPC call to the "productOnDepot_getObjects" with the depot list.
	"""
	return service_client.jsonrpc("productOnDepot_getObjects", [[], {"depotId": list(depot_list)}])


def download_with_progress(url: str, destination: Path) -> None:
	"""
	Downloads a file from the given URL to the specified destination with a progress bar.
	"""
	with get_progress() as progress:
		downloaded_file = download(
			url, destination, progress_callback=ProgressCallbackAdapter(progress, f"Downloading '{url}'...").progress_callback
		)
	logger.info("Downloaded file to %s", downloaded_file)


def download_package(url: str, temp_dir: Path) -> str:
	"""
	Downloads a package and its related files from the given URL to the specified temporary directory.
	Extracts the package if it is an archive and moves relevant files to the temporary directory.
	"""
	parsed_url = urlparse(url)
	filename = Path(parsed_url.path).name
	local_opsi_file = temp_dir / filename

	download_with_progress(url, temp_dir)

	if filename.endswith(".opsi"):
		for ext in [".md5", ".zsync"]:
			download_with_progress(url + ext, temp_dir)
	elif any(
		filename.endswith(ext)
		for ext in (".tar", ".gz", ".gzip", ".bz2", ".bzip2", ".zstd", ".cpio", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tar.xz", ".txz")
	):
		extract_dir = temp_dir / f"extract_{filename}"
		with get_progress() as progress:
			extract_archive(
				archive=local_opsi_file,
				destination=extract_dir,
				progress_listener=PackageProgressListener(progress, f"Extracting '{filename}'..."),
			)
		logger.info("Extracted file %s to %s", filename, extract_dir)

		relevant_files = (file for file in extract_dir.rglob("*") if file.suffix in {".opsi", ".md5", ".zsync"})
		for file in relevant_files:
			final_path = temp_dir / file.name
			shutil.move(str(file), final_path)
			logger.info("Moved %s to %s", file, final_path)
			if file.suffix == ".opsi":
				local_opsi_file = final_path

	return str(local_opsi_file)


def process_local_packages(packages: list[str], temp_dir: Path) -> list[str]:
	"""
	Download packages if necessary and return local paths.
	"""
	local_packages = set()
	for package in packages:
		parsed_url = urlparse(package)
		if parsed_url.scheme in ("http", "https"):
			local_package = download_package(package, temp_dir)
			local_packages.add(local_package)
		else:
			package_path = Path(package)
			if not package_path.exists():
				raise FileNotFoundError(f"Package '{package}' not found	")
			local_packages.add(package)
	return list(local_packages)


def map_and_sort_packages(packages: list[str]) -> dict[Path, OpsiPackage]:
	"""
	Maps a list of package paths to OpsiPackage objects and sorts them based on their dependencies.

	Each package is placed after its dependencies in the dictionary.
	"""
	path_to_opsipackage: dict[Path, OpsiPackage] = {}
	product_id_to_path: dict[str, Path] = {}
	with get_progress() as progress:
		num_packages = len(packages)
		task = progress.add_task(f"Analyzing {num_packages} package{'s' if num_packages > 1 else ''}...", total=num_packages)
		for pkg in packages:
			logger.info("Analyzing package: '%s'", pkg)
			try:
				opsi_package = OpsiPackage(Path(pkg))
			except Exception as err:
				logger.error(err, exc_info=True)
				raise RuntimeError(f"Failed to analyze package '{pkg}': {err}") from err

			path_to_opsipackage[Path(pkg)] = opsi_package
			product_id_to_path[opsi_package.product.id] = Path(pkg)

			progress.update(task, advance=1)

	result = {}
	visited = set()

	def visit(path: Path) -> None:
		if path in visited:
			return
		visited.add(path)
		opsi_package = path_to_opsipackage[path]
		for dep in opsi_package.package_dependencies or []:
			dep_path = product_id_to_path.get(dep.package)
			if dep_path is None:
				logger.warning(
					"Dependency '%s' for package '%s' is not specified locally. Assuming it is already installed on the server.",
					dep.package,
					opsi_package.product.id,
				)
				continue
			visit(dep_path)
		result[path] = opsi_package

	for path in path_to_opsipackage:
		try:
			visit(path)
		except Exception as err:
			logger.error(err, exc_info=True)
			raise RuntimeError(f"Failed to analyze package '{path}': {err}") from err
	return result


def check_locked_products(
	service_client: ServiceClient,
	depot_objects: list[OpsiDepotserver],
	path_to_opsipackage_dict: dict[Path, OpsiPackage],
) -> None:
	"""
	Checks if the packages are locked on the depots and raises an error if any are found.
	"""
	if not depot_objects:
		raise ValueError("No depots found matching the supplied depot selection.")
	product_list = [opsi_package.product.id for opsi_package in path_to_opsipackage_dict.values()]
	depot_id_list = [depot.id for depot in depot_objects]
	locked_products = service_client.jsonrpc(
		"productOnDepot_getObjects", [["productId", "depotId"], {"productId": product_list, "depotId": depot_id_list, "locked": True}]
	)
	if locked_products:
		metadata = COMMAND_METADATA["package_install"]
		logger.error("Locked products found: %s", locked_products)
		console_print("Locked products:", output_type=OutputType.ERROR_MESSAGE)
		write_output(data=[{"productId": p.productId, "depotId": p.depotId} for p in locked_products], metadata=metadata)
		raise ValueError("Locked products found, use --force to install anyway")


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


def update_product_property_defaults_interactively(path_to_opsipackage_dict: dict[Path, OpsiPackage]) -> None:
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


@lru_cache(maxsize=100)
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


@lru_cache(maxsize=100)
def get_md5_file(*, package_path: Path, temp_dir: Path) -> tuple[Path, str]:
	"""
	Create the MD5 for the package in a temporary path.
	Also checks if the local MD5 file differs from the temporary one.
	Returns the MD5 file path and the checksum.
	"""
	md5_file = package_path.with_suffix(".opsi.md5")

	tmp_md5_file = temp_dir / md5_file.name
	if not tmp_md5_file.exists():
		logger.info("Creating MD5 file for package %s in temporary path %s", package_path, temp_dir)
		tmp_md5_file = create_package_md5_file(package_path, filename=tmp_md5_file)
	else:
		logger.info("Using existing temporary MD5 file %s", tmp_md5_file)

	if md5_file.exists():
		local_md5 = md5_file.read_text()
		tmp_md5 = tmp_md5_file.read_text()
		if local_md5 != tmp_md5:
			logger.warning("Local MD5 file differs from the temporary one.")

	return tmp_md5_file, tmp_md5_file.read_text()


@lru_cache(maxsize=100)
def get_zsync_file(*, package_path: Path, temp_dir: Path) -> Path:
	"""
	Create the zsync file for the package in a temporary path.
	Also checks if the local zsync file differs from the temporary one.
	Returns the zsync file path.
	"""
	zsync_file = package_path.with_suffix(".opsi.zsync")

	tmp_zsync_file = temp_dir / zsync_file.name
	if not tmp_zsync_file.exists():
		logger.info("Creating zsync file for package %s in temporary path %s", package_path, temp_dir)
		tmp_zsync_file = create_package_zsync_file(package_path, filename=tmp_zsync_file)
	else:
		logger.info("Using existing temporary zsync file %s", tmp_zsync_file)

	if zsync_file.exists():
		local_zsync = zsync_file.read_text(encoding="utf-8", errors="ignore")
		tmp_zsync = tmp_zsync_file.read_text(encoding="utf-8", errors="ignore")
		if local_zsync != tmp_zsync:
			logger.warning("Local zsync file differs from the temporary one.")

	return tmp_zsync_file


def check_pkg_existence_and_integrity(
	*,
	depot_connection: ServiceClient,
	dest_package_name: str,
	package_size: int,
	local_checksum: str,
) -> bool:
	"""
	Check if the package already exists in the repository and has the same size and checksum. If it does, skip the upload.
	"""
	logger.info("Checking package existence and integrity in the repository")
	repo_contents = depot_connection.webdav_content("/repository")
	existing_packages = [rc for rc in repo_contents if rc.name == dest_package_name]
	if not existing_packages:
		return False

	if existing_packages[0].size != package_size:
		logger.info("Size of source and destination differs.")
		return False

	remote_checksum = depot_connection.jsonrpc("depot_getMD5Sum", [DEPOT_REPOSITORY_PATH + "/" + dest_package_name])
	if local_checksum != remote_checksum:
		logger.info("Checksum of source and destination differs.")
		return False

	logger.notice("Package '%s' already exists in the repository with matching size and checksum. Skipping upload.", dest_package_name)
	console_print(
		f"Package '{dest_package_name}' already exists in the repository with matching size and checksum. Skipping upload.",
		output_type=OutputType.MESSAGE,
	)
	return True


def check_disk_space(*, depot_connection: ServiceClient, depot_id: str, package_size: int) -> None:
	"""
	Check if there is enough disk space on the depot for the package.
	"""
	logger.info("Checking disk space on depot '%s'", depot_id)
	available_space = depot_connection.jsonrpc("depot_getDiskSpaceUsage", [DEPOT_REPOSITORY_PATH])["available"]
	if available_space < package_size:
		logger.error(
			"Insufficient disk space on depot '%s'. Needed: %d bytes, available: %d bytes", depot_id, package_size, available_space
		)
		raise ValueError(f"Insufficient disk space on depot '{depot_id}'. Needed: {package_size} bytes, available: {available_space} bytes")


def cleanup_packages_from_repo(*, depot_connection: ServiceClient, product_id: str, exclude_package_name: str | None = None) -> None:
	"""
	Deletes packages from the depot repository.

	If `exclude_package_name` is provided, it excludes that package and its .md5 and .zsync files from deletion.
	Otherwise, it deletes all packages with the given product ID.
	"""
	exclude_files = (
		{exclude_package_name, f"{exclude_package_name}.md5", f"{exclude_package_name}.zsync"} if exclude_package_name else set()
	)

	for repo_content in depot_connection.webdav_content("/repository"):
		if repo_content.name in exclude_files or not repo_content.name.endswith((".opsi", ".opsi.md5", ".opsi.zsync")):
			continue

		basename = repo_content.name.rsplit(".opsi", 1)[0]
		if "_" not in basename:
			continue
		repo_product_id = basename.rsplit("_", 1)[0]

		if repo_product_id == product_id:
			logger.notice("Deleting package %s from depot", repo_content.path)
			depot_connection.delete(repo_content.path)


def validate_upload_and_check_disk_space(
	*, depot_connection: ServiceClient, depot_id: str, local_checksum: str, dest_package_name: str
) -> None:
	"""
	Validates the upload by comparing the checksums and also checks the disk space on the depot. If the disk space usage is above 90%, a warning is logged.
	"""
	logger.info("Validating upload and checking disk space")
	remote_checksum = depot_connection.jsonrpc("depot_getMD5Sum", [DEPOT_REPOSITORY_PATH + "/" + dest_package_name])
	if local_checksum != remote_checksum:
		logger.error("MD5sum mismatch: local='%s', remote='%s' after upload to depot '%s'", local_checksum, remote_checksum, depot_id)
		raise ValueError(f"MD5sum mismatch: local='{local_checksum}', remote='{remote_checksum}' after upload to depot '{depot_id}'")

	usage = depot_connection.jsonrpc("depot_getDiskSpaceUsage", [DEPOT_REPOSITORY_PATH])["usage"]
	if usage >= 0.9:
		logger.warning("Filesystem usage at %d%% on depot '%s'", int(usage * 100), depot_id)


def upload_to_repository(
	*,
	depot_connection: ServiceClient,
	depot_id: str,
	source_package: Path,
	dest_package_name: str,
	temp_dir: Path,
) -> None:
	"""
	Uploads a package to the depot's repository.
	"""
	md5_file, local_checksum = get_md5_file(package_path=source_package, temp_dir=temp_dir)
	package_size = source_package.stat().st_size

	if check_pkg_existence_and_integrity(
		depot_connection=depot_connection, dest_package_name=dest_package_name, package_size=package_size, local_checksum=local_checksum
	):
		return

	check_disk_space(depot_connection=depot_connection, depot_id=depot_id, package_size=package_size)

	zsync_file = get_zsync_file(package_path=source_package, temp_dir=temp_dir)

	for file in [source_package, md5_file, zsync_file]:
		filename = dest_package_name
		if file == md5_file:
			filename = f"{dest_package_name}.md5"
		elif file == zsync_file:
			filename = f"{dest_package_name}.zsync"

		logger.notice("Starting upload of file %r to depot %r", filename, depot_id)

		with get_progress() as progress:
			depot_connection.upload(
				file,
				f"/repository/{filename}",
				progress_callback=ProgressCallbackAdapter(progress, f"Uploading '{filename}' to depot '{depot_id}'...").progress_callback,
			)

		logger.notice("Finished upload of file %r to depot %r", filename, depot_id)

	cleanup_packages_from_repo(
		depot_connection=depot_connection, product_id=OpsiPackage(source_package).product.id, exclude_package_name=dest_package_name
	)
	validate_upload_and_check_disk_space(
		depot_connection=depot_connection, depot_id=depot_id, local_checksum=local_checksum, dest_package_name=dest_package_name
	)


def install_package(
	*,
	depot_connection: ServiceClient,
	depot_id: str,
	dest_package_name: str,
	force: bool,
	property_default_values: dict[str, list[Any]],
	force_product_name: str | None = None,
) -> None:
	"""
	Installs a package on a depot.
	"""
	remote_package_file = DEPOT_REPOSITORY_PATH + "/" + dest_package_name
	installation_params = [remote_package_file, str(force), property_default_values, None, force_product_name]
	logger.notice("Starting installation of package %s to depot %s", dest_package_name, depot_id)
	with get_progress() as progress:
		task = progress.add_task(f"Installing '{dest_package_name}' on depot '{depot_id}'...", total=None)
		depot_connection.jsonrpc("depot_installPackage", installation_params)
		progress.update(task, total=1, completed=1)
	logger.notice("Finished installation of package %s to depot %s", dest_package_name, depot_id)


def uninstall_package(
	*,
	depot_connection: ServiceClient,
	depot_id: str,
	product_id: str,
	force: bool,
	delete_files: bool,
) -> None:
	"""
	Uninstalls a package from a depot.
	"""
	uninstallation_params = [product_id, str(force), str(delete_files)]
	logger.notice("Starting uninstallation of product %s from depot %s", product_id, depot_id)
	with get_progress() as progress:
		task = progress.add_task(f"Uninstalling '{product_id}' from depot '{depot_id}'...", total=100)
		depot_connection.jsonrpc("depot_uninstallPackage", uninstallation_params)
		progress.update(task, completed=100)
	logger.notice("Finished uninstallation of product %s from depot %s", product_id, depot_id)


def handle_action_request(*, service_client: ServiceClient, depot_id: str, product: Product, action_request: str, dependency: bool) -> None:
	if not validate_action_request(product, action_request):
		return

	clients_from_depot = get_clients_from_depot(service_client, depot_id)
	if not clients_from_depot:
		logger.warning("No clients found for depot %s. Skipping setting action request.", depot_id)
		console_print(f"No clients found for depot '{depot_id}'. Skipping setting action request.", output_type=OutputType.WARNING_MESSAGE)
		return

	product_on_clients = get_product_on_clients(service_client, tuple(clients_from_depot), product.id)
	if not product_on_clients:
		logger.warning("No productOnClient found for product %s. Skipping setting action request.", product.id)
		console_print(
			f"No productOnClient found for product '{product.id}'. Skipping setting action request.", output_type=OutputType.WARNING_MESSAGE
		)
		return

	logger.notice("Setting action request to '%s' for product %s on depot %s", action_request, product.id, depot_id)
	with get_progress() as progress:
		task = progress.add_task(
			f"Setting action request to '{action_request}' for product '{product.id}' on depot '{depot_id}'...",
			total=100,
		)
		set_action_request(service_client, product.id, action_request, product_on_clients, dependency)
		progress.update(task, completed=100)
	logger.notice("Finished setting action request to '%s' for product %s on depot %s", action_request, product.id, depot_id)


@lru_cache(maxsize=100)
def validate_action_request(product: Product, action_request: str) -> bool:
	if action_request == "update" and not product.getUpdateScript() or action_request == "setup" and not product.getSetupScript():
		logger.warning("%s script not found for product '%s'.", action_request.capitalize(), product.id)
		console_print(f"{action_request.capitalize()} script not found for product '{product.id}'.", output_type=OutputType.WARNING_MESSAGE)
		return False
	return True


@lru_cache(maxsize=100)
def get_clients_from_depot(service_client: ServiceClient, depot_id: str) -> list[str]:
	return [client_to_depot["clientId"] for client_to_depot in service_client.jsonrpc("configState_getClientToDepotserver", [depot_id])]


@lru_cache(maxsize=100)
def get_product_on_clients(service_client: ServiceClient, clients_from_depot: tuple[str, ...], product_id: str) -> list[ProductOnClient]:
	return service_client.jsonrpc(
		"productOnClient_getObjects",
		[[], {"clientId": list(clients_from_depot), "productId": product_id, "installationStatus": "installed"}],
	)


def set_action_request(
	service_client: ServiceClient, product_id: str, action_request: str, product_on_clients: list[ProductOnClient], dependency: bool
) -> None:
	if dependency:
		logger.notice("Setting action request to '%s' with dependencies for product %s", action_request, product_id)
		for poc in product_on_clients:
			service_client.jsonrpc("setProductActionRequestWithDependencies", [product_id, poc.clientId, action_request])
	else:
		for poc in product_on_clients:
			poc.actionRequest = action_request
			poc.modificationTime = opsi_timestamp()
		service_client.jsonrpc("productOnClient_updateObjects", [product_on_clients])


def initialize_opsi_package(
	service_client: ServiceClient, product_on_depot: ProductOnDepot, depot_id: str, properties: Literal["keep", "ask", "package"]
) -> OpsiPackage:
	"""
	Initializes an OpsiPackage object by populating it with product, properties, and dependencies fetched from ServiceClient.
	It also updates property default values based on the specified option.
	"""

	logger.notice("Initializing OpsiPackage for %s", product_on_depot.productId)

	product: Product = service_client.jsonrpc(
		"product_getObjects",
		[
			[],
			{
				"id": [product_on_depot.productId],
				"productVersion": product_on_depot.productVersion,
				"packageVersion": product_on_depot.packageVersion,
			},
		],
	)[0]
	product_properties: list[ProductProperty] = service_client.jsonrpc(
		"productProperty_getObjects",
		[
			[],
			{
				"productId": product_on_depot.productId,
				"productVersion": product_on_depot.productVersion,
				"packageVersion": product_on_depot.packageVersion,
			},
		],
	)
	product_dependencies: list[ProductDependency] = service_client.jsonrpc(
		"productDependency_getObjects",
		[
			[],
			{
				"productId": product_on_depot.productId,
				"productVersion": product_on_depot.productVersion,
				"packageVersion": product_on_depot.packageVersion,
			},
		],
	)

	opsi_package = OpsiPackage()
	opsi_package.product = product
	opsi_package.product_properties = product_properties
	opsi_package.product_dependencies = product_dependencies

	properties_dict = {product_property.propertyId: product_property for product_property in opsi_package.product_properties}
	if properties == "keep":
		for product_property_state in service_client.jsonrpc(
			"productPropertyState_getObjects",
			[[], {"productId": opsi_package.product.id, "objectId": depot_id}],
		):
			properties_dict[product_property_state.propertyId].defaultValues = product_property_state.values or []
		opsi_package.product_properties = list(properties_dict.values())
	elif properties == "ask":
		update_product_property_defaults_interactively({Path(product_on_depot.productId): opsi_package})  # using a  dummy path as key

	return opsi_package


def generate_control_files(opsi_package: OpsiPackage, temp_dir: Path) -> None:
	"""
	Create an 'OPSI' directory in the specified temporary directory and generate 'control.toml' file inside it.
	"""

	logger.notice("Generating control files for %s", opsi_package.product.id)
	with get_progress() as progress:
		task = progress.add_task(f"Generating control files for '{opsi_package.product.id}'...", total=None)

		opsi_dir = temp_dir / "OPSI"
		opsi_dir.mkdir(parents=True, exist_ok=True)

		control_toml = opsi_dir / "control.toml"
		opsi_package.generate_control_file(control_toml)

		progress.update(task, total=1, completed=1)
	logger.notice("Finished generating control files for %s", opsi_package.product.id)


def download_depot_files(depot_object: OpsiDepotserver, product_id: str, temp_dir: Path) -> None:
	"""
	Download files for a specified product from the depot repository and store them in a temporary directory.
	"""
	logger.notice("Downloading depot files for %s", product_id)
	with get_progress() as progress:
		task = progress.add_task(f"Downloading depot files for '{product_id}'...", total=None)

		depot_connection = get_depot_connection(depot_object)
		depot_data = depot_connection.webdav_content(f"/depot/{product_id}")

		client_data_dir = temp_dir / "CLIENT_DATA"
		client_data_dir.mkdir(parents=True, exist_ok=True)

		for content in depot_data:
			if not content.name.endswith(".files"):
				depot_connection.download(content.path, client_data_dir)

		progress.update(task, total=1, completed=1)
	logger.notice("Finished downloading depot files for %s", product_id)
