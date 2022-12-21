"""
opsi-cli basic command line interface for opsi

client_action_worker
"""

from typing import Dict, List, Optional, Set

from opsicommon.logging import logger  # type: ignore[import]
from opsicommon.objects import ProductOnClient

from opsicli.config import config

from .client_action_worker import ClientActionWorker

STATIC_EXCLUDE_PRODUCTS = [
	"opsi-winst",
	"opsi-auto-update",
	"opsi-script",
	"shutdownwanted",
	"windows10-upgrade",
	"activate-win",
	"opsi-script-test",
	"opsi-bootimage-local",
	"opsi-uefi-netboot",
	"opsi-wan-config-on",
	"opsi-wan-config-off",
	"opsi-winpe",
	"win10-sysprep-app-update-blocker",
	"windomain",
]

ACTION_REQUEST_SCRIPTS = [
	"setupScript",
	"uninstallScript",
	"updateScript",
	"alwaysScript",
	"onceScript",
	"customScript",
]


class SetActionRequestWorker(ClientActionWorker):
	def __init__(self, **kwargs):
		super().__init__(
			kwargs.get("clients"),
			kwargs.get("client_groups"),
			kwargs.get("exclude_clients"),
			kwargs.get("exclude_client_groups")
		)
		self.products: List[str] = []
		self.products_with_only_uninstall: List[str] = []
		self.depot_versions: Dict[str, Dict[str, str]] = {}
		self.product_action_scripts: Dict[str, List[str]] = {}
		self.client_to_depot: Dict[str, str] = {}
		self.depending_products: Set[str] = set()
		self.request_type = "setup"
		for single_client_to_depot in self.service.jsonrpc("configState_getClientToDepotserver", [[], self.clients]):
			self.client_to_depot[single_client_to_depot["clientId"]] = single_client_to_depot["depotId"]
		logger.trace("ClientToDepot mapping: %s", self.client_to_depot)
		for entry in self.service.jsonrpc("productOnDepot_getObjects"):
			if not self.depot_versions.get(entry["depotId"]):
				self.depot_versions[entry["depotId"]] = {}
			self.depot_versions[entry["depotId"]][entry["productId"]] = f"{entry['productVersion']}-{entry['packageVersion']}"
		logger.trace("Product versions on depots: %s", self.depot_versions)
		for pdep in self.service.jsonrpc("productDependency_getObjects"):
			self.depending_products.add(pdep["productId"])
		for product in self.service.jsonrpc("product_getObjects"):
			# store the available action request scripts (strip "Script" at the end of the property)
			self.product_action_scripts[product["id"]] = [key[:-6] for key in ACTION_REQUEST_SCRIPTS if product.get(key)]
		logger.trace("Products with dependencies: %s", self.depending_products)

	def product_ids_from_group(self, group: str) -> List[str]:
		result = self.service.jsonrpc("group_getObjects", [[], {"id": group, "type": "ProductGroup"}])
		if not result:
			raise ValueError(f"Product group '{group}' not found")
		return [mapping["objectId"] for mapping in self.service.jsonrpc("objectToGroup_getObjects", [[], {"groupId": result[0]["id"]}])]

	def determine_products(  # pylint: disable=too-many-arguments
		self,
		products_string: Optional[str] = None,
		exclude_products_string: Optional[str] = None,
		product_groups_string: Optional[str] = None,
		exclude_product_groups_string: Optional[str] = None,
		use_default_excludes: bool = True
	) -> None:
		exclude_products = []
		if use_default_excludes:
			exclude_products = STATIC_EXCLUDE_PRODUCTS
		products: List[str] = []
		if products_string:
			products = [entry.strip() for entry in products_string.split(",")]
		if product_groups_string:
			for group in [entry.strip() for entry in product_groups_string.split(",")]:
				products.extend(self.product_ids_from_group(group))
		if products_string or product_groups_string:
			logger.info("Limiting handled products to %s", products)
		if exclude_products_string:
			exclude_products.extend([entry.strip() for entry in exclude_products_string.split(",")])
		if exclude_product_groups_string:
			for group in [entry.strip() for entry in exclude_product_groups_string.split(",")]:
				exclude_products.extend(self.product_ids_from_group(group))
		logger.info("List of excluded products: %s", exclude_products)
		product_objects = self.service.jsonrpc("product_getObjects", [[], {"type": "LocalbootProduct", "id": products or None}])
		self.products = [entry["id"] for entry in product_objects if entry["id"] not in exclude_products]
		self.products_with_only_uninstall = [
			entry["id"]
			for entry in product_objects
			if entry.get("uninstallScript") and
			not entry.get("setupScript") and
			not entry.get("onceScript") and
			not entry.get("customScript") and
			not entry.get("updateScript") and
			not entry.get("alwaysScript") and
			not entry.get("userLoginScript") and
			entry["id"] in self.products
		]
		logger.notice("Handling products %s", self.products)

	def set_single_action_request(
		self, product_on_client: Dict[str, str],
		request_type: Optional[str] = None,
		force: bool = False
	) -> List[Dict[str, str]]:
		if not force and product_on_client["actionRequest"] not in (None, "none"):
			logger.info(
				"Skipping %s %s as an actionRequest is set: %s",
				product_on_client["productId"],
				product_on_client["clientId"],
				product_on_client["actionRequest"],
			)
			return []  # existing actionRequests are left untouched
		if request_type and request_type.lower() != "none" and request_type not in self.product_action_scripts[product_on_client["productId"]]:
			logger.warning(
				"Skipping %s %s as the package does not have a script for: %s",
				product_on_client["productId"],
				product_on_client["clientId"],
				request_type,
			)
			return []

		if product_on_client["productId"] in self.depending_products:
			logger.notice(
				"Setting '%s' ProductActionRequest with Dependencies: %s -> %s",
				request_type or self.request_type,
				product_on_client["productId"],
				product_on_client["clientId"]
			)
			if not config.dry_run:
				self.service.jsonrpc(
					"setProductActionRequestWithDependencies",
					[product_on_client["productId"], product_on_client["clientId"], request_type or self.request_type]
				)
			return []  # no need to update the POC
		logger.notice(
			"Setting '%s' ProductActionRequest: %s -> %s",
			request_type or self.request_type,
			product_on_client["productId"],
			product_on_client["clientId"],
		)
		if not config.dry_run:
			product_on_client["actionRequest"] = request_type or self.request_type
		return [product_on_client]

	def set_action_requests_for_all(
		self,
		clients: List[str], products: List[str],
		request_type: Optional[str] = None,
		force: bool = False
	) -> List[Dict[str, str]]:
		new_pocs = []
		existing_pocs: Dict[str, Dict[str, Dict[str, str]]] = {}
		for poc in self.service.jsonrpc(
			"productOnClient_getObjects",
			[[], {"clientId": self.clients or None, "productType": "LocalbootProduct", "productId": self.products}],
		):
			if poc["clientId"] not in existing_pocs:
				existing_pocs[poc["clientId"]] = {}
			existing_pocs[poc["clientId"]].update({poc["productId"]: poc})
		for client in clients:
			for product in products:
				poc = existing_pocs.get(client, {}).get(product, None) or ProductOnClient(
					productId=product,
					productType="LocalbootProduct",
					clientId=client,
					installationStatus="not_installed",
					actionRequest=None,
				).to_hash()
				print(poc)
				new_pocs.extend(self.set_single_action_request(poc, request_type or self.request_type, force=force))
		return new_pocs

	def set_action_request(self, **kwargs) -> None:  # pylint: disable=too-many-branches
		if config.dry_run:
			logger.notice("Operating in dry-run mode - not performing any actions")

		self.request_type = kwargs.get("request_type", self.request_type)
		self.determine_products(
			kwargs.get("products"),
			kwargs.get("exclude_products"),
			kwargs.get("product_groups"),
			kwargs.get("exclude_product_groups"),
			use_default_excludes=kwargs.get("where_outdated", False) or kwargs.get("where_failed", False)
		)
		if not self.products:
			raise ValueError("No products selected")
		if kwargs.get("uninstall_where_only_uninstall"):
			logger.notice("Uninstalling products (where installed): %s", self.products_with_only_uninstall)

		new_pocs = []
		if kwargs.get("where_failed") or kwargs.get("where_outdated") or kwargs.get("uninstall_where_only_uninstall"):
			modified_clients = set()
			for entry in self.service.jsonrpc(
				"productOnClient_getObjects",
				[[], {"clientId": self.clients or None, "productType": "LocalbootProduct", "productId": self.products}],
			):
				logger.debug(
					"Checking %s (%s) on %s", entry["productId"],
					f"{entry['productVersion']}-{entry['packageVersion']}",
					entry["clientId"],
				)
				try:
					available = self.depot_versions[self.client_to_depot[entry["clientId"]]][entry["productId"]]
				except KeyError:
					logger.error("Skipping check of %s %s (product not available on depot)", entry["clientId"], entry["productId"])
					continue
				if kwargs.get("uninstall_where_only_uninstall") and entry["productId"] in self.products_with_only_uninstall:
					new_pocs.extend(self.set_single_action_request(entry, "uninstall"))
					modified_clients.add(entry["clientId"])
				elif kwargs.get("where_failed") and entry["actionResult"] == "failed":
					new_pocs.extend(self.set_single_action_request(entry))
					modified_clients.add(entry["clientId"])
				elif (
					kwargs.get("where_outdated") and entry["installationStatus"] == "installed" and
					f"{entry['productVersion']}-{entry['packageVersion']}" != available
				):
					new_pocs.extend(self.set_single_action_request(entry))
					modified_clients.add(entry["clientId"])
			if kwargs.get("setup_on_action") and modified_clients:
				setup_on_action_products = [entry.strip() for entry in str(kwargs.get("setup_on_action")).split(",")]
				logger.notice("Setting setup for all modified clients and products: %s", setup_on_action_products)
				new_pocs.extend(self.set_action_requests_for_all(list(modified_clients), setup_on_action_products, "setup"))
		# if neither where_failed nor where_outdated nor uninstall_where_only_uninstall is set, set action request for every selected client
		else:
			if not kwargs.get("products") and not kwargs.get("product_groups"):
				raise ValueError("When unconditionally setting actionRequests, you must supply --products or --product-groups.")
			new_pocs.extend(self.set_action_requests_for_all(self.clients, self.products, force=True))

		if not new_pocs:
			logger.info("Nothing to do.")
		elif not config.dry_run:
			logger.debug("Updating ProductOnClient")
			self.service.jsonrpc("productOnClient_updateObjects", [new_pocs])
