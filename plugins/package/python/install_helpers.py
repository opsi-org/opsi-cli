"""
Support functions for installing packages.
"""

from collections import defaultdict
from pathlib import Path
from typing import Any

from opsicommon.client.opsiservice import ServiceClient
from opsicommon.logging import get_logger
from opsicommon.package import OpsiPackage

from OPSI.Util.Repository import getRepository  # type: ignore[import]

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
	For example, the package name "test2_1.0-6~custom1.opsi" will be fixed to "test2_1.0-6.opsi".
	"""
	package_name = package_path.stem
	if '~' in package_name:
		fixed_name = package_name.split('~')[0] + ".opsi"
		logger.notice(f"Custom package detected: {package_name}. Fixed to: {fixed_name}")
		return fixed_name
	else:
		return f"{package_name}.opsi"


def upload_to_repository(depot: Any, package_path: Path, user_agent: str) -> None:
	"""
	Uploads a package to the depot's repository.
	"""
	logger.info("Uploading package %s to repository", package_path)
	print(f"Uploading package {package_path} to repository")
	repository = getRepository(
		url=depot.repositoryRemoteUrl,
		username=depot.id,
		password=depot.opsiHostKey,
		maxBandwidth=(max(depot.maxBandwidth or 0, 0)) * 1000,
		application=user_agent,
		readTimeout=24 * 3600,
	)

	print(f"Repository: {repository.content()}")


def install_package(depot: Any, package_path: Path) -> None:
	"""
	Installs a package on a depot.
	"""
	logger.info("Installing package %s on depot %s", package_path, depot.id)
	print(f"Installing package {package_path} on depot {depot.id}")
	print(depot.repositoryLocalUrl)
