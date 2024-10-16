"""
Support functions for installing packages.
"""

import shutil
from contextlib import nullcontext
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from opsicommon.client.opsiservice import ServiceClient
from opsicommon.logging import get_logger
from opsicommon.objects import BoolProductProperty, OpsiDepotserver, ProductProperty
from opsicommon.package import OpsiPackage
from opsicommon.package.archive import extract_archive
from opsicommon.package.associated_files import create_package_md5_file, create_package_zsync_file
from rich.progress import Progress

from opsicli.config import config
from opsicli.io import get_console, prompt
from opsicli.utils import ProgressCallbackAdapter, download

from .package_progress import PackageProgressListener

DEPOT_REPOSITORY_PATH = "/var/lib/opsi/repository"


logger = get_logger("opsicli")


def get_depot_objects(service_client: ServiceClient, depots: str) -> list[OpsiDepotserver]:
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


def download_with_progress(url: str, destination: Path) -> None:
	"""
	Downloads a file from the given URL to the specified destination with a progress bar.
	"""
	with nullcontext() if config.quiet else Progress() as progress:  # type: ignore[attr-defined]
		progress_callback = ProgressCallbackAdapter(progress, f"Downloading '{url}'...").progress_callback if not config.quiet else None
		downloaded_file = download(url, destination, progress_callback=progress_callback)
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
		for ext in {".tar", ".gz", ".gzip", ".bz2", ".bzip2", ".zstd", ".cpio", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tar.xz", ".txz"}
	):
		extract_dir = temp_dir / f"extract_{filename}"
		with nullcontext() if config.quiet else Progress() as progress:  # type: ignore[attr-defined]
			progress_listener = None
			if not config.quiet:
				progress_listener = PackageProgressListener(progress, f"Extracting '{filename}'...")

			extract_archive(
				archive=local_opsi_file,
				destination=extract_dir,
				progress_listener=progress_listener,
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
	path_to_opsipackage_dict = {Path(pkg): OpsiPackage(Path(pkg)) for pkg in packages}
	product_id_to_path = {pkg.product.id: path for path, pkg in path_to_opsipackage_dict.items()}
	result = {}
	visited = set()

	def visit(path: Path) -> None:
		if path in visited:
			return
		visited.add(path)
		opsi_package = path_to_opsipackage_dict[path]
		for dep in opsi_package.package_dependencies or []:
			dep_path = product_id_to_path.get(dep.package)
			if dep_path is None:
				raise ValueError(f"Dependency '{dep.package}' for package '{opsi_package.product.id}' is not specified.")
			visit(dep_path)
		result[path] = opsi_package

	for path in path_to_opsipackage_dict:
		visit(path)
	return result


def check_locked_products(
	service_client: ServiceClient,
	depot_objects: list[OpsiDepotserver],
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
def get_md5_file(package_path: Path, temp_dir: Path) -> tuple[Path, str]:
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
def get_zsync_file(package_path: Path, temp_dir: Path) -> Path:
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
	get_console().print(f"Package '{dest_package_name}' already exists in the repository with matching size and checksum. Skipping upload.")
	return True


def check_disk_space(depot_connection: ServiceClient, depot_id: str, package_size: int) -> None:
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


def cleanup_packages_from_repo(depot_connection: ServiceClient, product_id: str, exclude_package_name: str | None = None) -> None:
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
	depot_connection: ServiceClient, depot_id: str, local_checksum: str, dest_package_name: str
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
	depot_connection: ServiceClient,
	depot_id: str,
	source_package: Path,
	dest_package_name: str,
	temp_dir: Path,
) -> None:
	"""
	Uploads a package to the depot's repository.
	"""
	md5_file, local_checksum = get_md5_file(source_package, temp_dir)
	package_size = source_package.stat().st_size

	if check_pkg_existence_and_integrity(depot_connection, dest_package_name, package_size, local_checksum):
		return

	check_disk_space(depot_connection, depot_id, package_size)

	zsync_file = get_zsync_file(source_package, temp_dir)

	for file in [source_package, md5_file, zsync_file]:
		filename = dest_package_name
		if file == md5_file:
			filename = f"{dest_package_name}.md5"
		elif file == zsync_file:
			filename = f"{dest_package_name}.zsync"

		logger.notice("Starting upload of file %r to depot %r", filename, depot_id)

		with nullcontext() if config.quiet else Progress() as progress:  # type: ignore[attr-defined]
			progress_callback = (
				ProgressCallbackAdapter(progress, f"Uploading '{filename}'...").progress_callback if not config.quiet else None
			)
			depot_connection.upload(file, f"/repository/{filename}", progress_callback=progress_callback)

		logger.notice("Finished upload of file %r to depot %r", filename, depot_id)

	cleanup_packages_from_repo(depot_connection, OpsiPackage(source_package).product.id, dest_package_name)
	validate_upload_and_check_disk_space(depot_connection, depot_id, local_checksum, dest_package_name)


def get_property_default_values(
	service_client: ServiceClient,
	depot_id: str,
	opsi_package: OpsiPackage,
	update_properties: bool,
) -> dict[str, list[Any]]:
	"""
	Get the default values for the product properties.

	If `update_properties` is True and in interactive mode, get user-updated values.
	Otherwise, fetch property states for the depot from `productPropertyState_getObjects`.
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
	depot_id: str,
	dest_package_name: str,
	force: bool,
	property_default_values: dict[str, list[Any]],
) -> None:
	"""
	Installs a package on a depot.
	"""
	remote_package_file = DEPOT_REPOSITORY_PATH + "/" + dest_package_name
	installation_params = [remote_package_file, str(force), property_default_values]
	logger.notice("Starting installation of package %s to depot %s", dest_package_name, depot_id)
	with nullcontext() if config.quiet else Progress() as progress:  # type: ignore[attr-defined]
		if not config.quiet:
			task = progress.add_task(f"Installing '{dest_package_name}' on depot '{depot_id}'...\n", total=None)
		depot_connection.jsonrpc("depot_installPackage", installation_params)
		if not config.quiet:
			progress.update(task, total=1, completed=1)
	logger.notice("Finished installation of package %s to depot %s", dest_package_name, depot_id)


def uninstall_package(
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
	with nullcontext() if config.quiet else Progress() as progress:  # type: ignore[attr-defined]
		if not config.quiet:
			task = progress.add_task(f"Uninstalling '{product_id}' from depot '{depot_id}'...\n", total=100)
		depot_connection.jsonrpc("depot_uninstallPackage", uninstallation_params)
		if not config.quiet:
			progress.update(task, completed=100)
	logger.notice("Finished uninstallation of product %s from depot %s", product_id, depot_id)
