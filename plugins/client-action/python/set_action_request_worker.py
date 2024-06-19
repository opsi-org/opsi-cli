"""
opsi-cli basic command line interface for opsi

client_action_worker
"""

from opsicommon.logging import get_logger
from opsicommon.objects import Product, ProductDependency, ProductGroup, ProductOnClient, ProductOnDepot

from opsicli.config import config

from .client_action_worker import ClientActionArgs, ClientActionWorker

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


logger = get_logger("opsicli")


class SetActionRequestWorker(ClientActionWorker):
	def __init__(self, args: ClientActionArgs) -> None:
		super().__init__(args)
		self.products: list[str] = []
		self.products_with_only_uninstall: list[str] = []
		self.depot_versions: dict[str, dict[str, str]] = {}
		self.product_action_scripts: dict[str, list[str]] = {}
		self.client_to_depot: dict[str, str] = {}
		self.depending_products: set[str] = set()
		self.request_type = "setup"

		for single_client_to_depot in self.service.jsonrpc("configState_getClientToDepotserver", [[], list(self.clients)]):
			self.client_to_depot[single_client_to_depot["clientId"]] = single_client_to_depot["depotId"]
		logger.trace("ClientToDepot mapping: %s", self.client_to_depot)

		product_on_depots: list[ProductOnDepot] = self.service.jsonrpc("productOnDepot_getObjects")
		for entry in product_on_depots:
			if not self.depot_versions.get(entry.depotId):
				self.depot_versions[entry.depotId] = {}
			self.depot_versions[entry.depotId][entry.productId] = f"{entry.productVersion}-{entry.packageVersion}"
		logger.trace("Product versions on depots: %s", self.depot_versions)

		product_dependencies: list[ProductDependency] = self.service.jsonrpc("productDependency_getObjects")
		for pdep in product_dependencies:
			self.depending_products.add(pdep.productId)

		products: list[Product] = self.service.jsonrpc("product_getObjects")
		for product in products:
			# store the available action request scripts (strip "Script" at the end of the property)
			self.product_action_scripts[product.id] = [key[:-6] for key in ACTION_REQUEST_SCRIPTS if getattr(product, key, None)]
		logger.trace("Products with dependencies: %s", self.depending_products)

	def product_ids_from_group(self, group: str) -> list[str]:
		product_groups: list[ProductGroup] = self.service.jsonrpc("group_getObjects", [[], {"id": group, "type": "ProductGroup"}])
		if not product_groups:
			raise ValueError(f"Product group '{group}' not found")
		return [mapping.objectId for mapping in self.service.jsonrpc("objectToGroup_getObjects", [[], {"groupId": product_groups[0].id}])]

	def determine_products(
		self,
		*,
		products_string: str | None = None,
		exclude_products_string: str | None = None,
		product_groups_string: str | None = None,
		exclude_product_groups_string: str | None = None,
		use_default_excludes: bool = True,
	) -> None:
		exclude_products = []
		if use_default_excludes:
			exclude_products = STATIC_EXCLUDE_PRODUCTS

		products: list[str] = []
		if products_string:
			products = [entry.strip() for entry in products_string.split(",")]
			for product in products:
				if product in exclude_products:
					logger.debug("Removing default excluded product %r from exclude list", product)
					exclude_products.remove(product)

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

		product_objects: list[Product] = self.service.jsonrpc(
			"product_getObjects", [[], {"type": "LocalbootProduct", "id": products or None}]
		)
		self.products = list(set((entry.id for entry in product_objects if entry.id not in exclude_products)))
		self.products_with_only_uninstall = [
			entry.id
			for entry in product_objects
			if entry.uninstallScript
			and not entry.setupScript
			and not entry.onceScript
			and not entry.customScript
			and not entry.updateScript
			and not entry.alwaysScript
			and not entry.userLoginScript
			and entry.id in self.products
		]
		logger.notice("Handling products %s", self.products)

	def set_single_action_request(
		self, product_on_client: ProductOnClient, request_type: str | None = None, force: bool = False
	) -> list[ProductOnClient]:
		if not force and product_on_client.actionRequest not in (None, "none"):
			logger.info(
				"Skipping %s %s as an actionRequest is set: %s",
				product_on_client.productId,
				product_on_client.clientId,
				product_on_client.actionRequest,
			)
			return []  # existing actionRequests are left untouched
		if request_type and request_type.lower() != "none" and request_type not in self.product_action_scripts[product_on_client.productId]:
			logger.warning(
				"Skipping %s %s as the package does not have a script for: %s",
				product_on_client.productId,
				product_on_client.clientId,
				request_type,
			)
			return []

		if product_on_client.productId in self.depending_products:
			logger.notice(
				"Setting '%s' ProductActionRequest with Dependencies: %s -> %s",
				request_type or self.request_type,
				product_on_client.productId,
				product_on_client.clientId,
			)
			if not config.dry_run:
				self.service.jsonrpc(
					"setProductActionRequestWithDependencies",
					[product_on_client.productId, product_on_client.clientId, request_type or self.request_type],
				)
			return []  # no need to update the POC
		logger.notice(
			"Setting '%s' ProductActionRequest: %s -> %s",
			request_type or self.request_type,
			product_on_client.productId,
			product_on_client.clientId,
		)
		# Remark: request_type="none" instead of None for compatibility with file backend
		if not config.dry_run:
			product_on_client.actionRequest = request_type or self.request_type
		return [product_on_client]

	def set_action_requests_for_all(
		self, clients: set[str], products: list[str], request_type: str | None = None, force: bool = False
	) -> list[ProductOnClient]:
		new_pocs: list[ProductOnClient] = []
		existing_pocs: dict[str, dict[str, ProductOnClient]] = {}
		pocs: list[ProductOnClient] = self.service.jsonrpc(
			"productOnClient_getObjects",
			[[], {"clientId": list(self.clients), "productType": "LocalbootProduct", "productId": self.products}],
		)
		for exisiting_poc in pocs:
			if exisiting_poc.clientId not in existing_pocs:
				existing_pocs[exisiting_poc.clientId] = {}
			existing_pocs[exisiting_poc.clientId].update({exisiting_poc.productId: exisiting_poc})

		for client_id in clients:
			for product in products:
				poc = existing_pocs.get(client_id, {}).get(product) or ProductOnClient(
					productId=product,
					productType="LocalbootProduct",
					clientId=client_id,
					installationStatus="not_installed",
					actionRequest=None,
				)
				new_pocs.extend(self.set_single_action_request(poc, request_type or self.request_type, force=force))
		return new_pocs

	def set_action_request(self, **kwargs: str) -> None:
		if config.dry_run:
			logger.notice("Operating in dry-run mode - not performing any actions")

		self.request_type = kwargs.get("request_type", self.request_type)
		self.determine_products(
			products_string=kwargs.get("products"),
			exclude_products_string=kwargs.get("exclude_products"),
			product_groups_string=kwargs.get("product_groups"),
			exclude_product_groups_string=kwargs.get("exclude_product_groups"),
			use_default_excludes=bool(kwargs.get("where_outdated", False)) or bool(kwargs.get("where_failed", False)),
		)
		if not self.products:
			raise ValueError("No products selected")
		if kwargs.get("uninstall_where_only_uninstall"):
			logger.notice("Uninstalling products (where installed): %s", self.products_with_only_uninstall)

		new_pocs: list[ProductOnClient] = []
		if kwargs.get("where_failed") or kwargs.get("where_outdated") or kwargs.get("uninstall_where_only_uninstall"):
			modified_clients = set()
			pocs: list[ProductOnClient] = self.service.jsonrpc(
				"productOnClient_getObjects",
				[[], {"clientId": list(self.clients), "productType": "LocalbootProduct", "productId": self.products}],
			)
			for poc in pocs:
				logger.debug(
					"Checking %s (%s) on %s",
					poc.productId,
					f"{poc.productVersion}-{poc.packageVersion}",
					poc.clientId,
				)
				try:
					available = self.depot_versions[self.client_to_depot[poc.clientId]][poc.productId]
				except KeyError:
					logger.error("Skipping check of %s %s (product not available on depot)", poc.clientId, poc.productId)
					continue
				if kwargs.get("uninstall_where_only_uninstall") and poc.productId in self.products_with_only_uninstall:
					new_pocs.extend(self.set_single_action_request(poc, "uninstall"))
					modified_clients.add(poc.clientId)
				elif kwargs.get("where_failed") and poc.actionResult == "failed":
					new_pocs.extend(self.set_single_action_request(poc))
					modified_clients.add(poc.clientId)
				elif (
					kwargs.get("where_outdated")
					and poc.installationStatus == "installed"
					and f"{poc.productVersion}-{poc.packageVersion}" != available
				):
					new_pocs.extend(self.set_single_action_request(poc))
					modified_clients.add(poc.clientId)
			if kwargs.get("setup_on_action") and modified_clients:
				setup_on_action_products = [entry.strip() for entry in str(kwargs.get("setup_on_action")).split(",")]
				logger.notice("Setting setup for all modified clients and products: %s", setup_on_action_products)
				new_pocs.extend(self.set_action_requests_for_all(modified_clients, setup_on_action_products, "setup"))
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
