"""
opsi-cli basic command line interface for opsi

client_action_worker
"""

from typing import Dict, List

from opsicommon.logging import logger  # type: ignore[import]

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
	"opsi-wan-config",
	"opsi-winpe",
	"win10-sysprep-app-update-blocker",
	"windomain",
]


class SetActionRequestWorker(ClientActionWorker):
	def __init__(self, **kwargs):
		super().__init__(kwargs.get("clients"), kwargs.get("client_groups"))
		self.products = []
		self.determine_products(kwargs.get("include_products"), kwargs.get("exclude_products"))
		self.depot_versions: Dict[str, str] = {}
		self.client_to_depot = {}
		self.depending_products = set()
		self.uninstall_products = []
		self.request_type = kwargs.get("request_type")
		for single_client_to_depot in self.service.execute_rpc("configState_getClientToDepotserver", [[], self.clients]):
			self.client_to_depot[single_client_to_depot["clientId"]] = single_client_to_depot["depotId"]
		logger.trace("ClientToDepot mapping: %s", self.client_to_depot)
		for entry in self.service.execute_rpc("productOnDepot_getObjects"):
			if not self.depot_versions.get(entry.depotId):
				self.depot_versions[entry.depotId] = {}
			self.depot_versions[entry.depotId][entry.productId] = entry.version
		logger.trace("Product versions on depots: %s", self.depot_versions)
		for pdep in self.service.execute_rpc("productDependency_getObjects"):
			self.depending_products.add(pdep.productId)
		logger.trace("Products with dependencies: %s", self.depending_products)

	def determine_products(self, include_products_string, exclude_products_string) -> None:
		exclude_products = STATIC_EXCLUDE_PRODUCTS
		include_products: List[str] = []
		if include_products_string:
			include_products = [entry.strip() for entry in include_products_string.split(",")]
			logger.notice("Limiting handled products to %s", include_products)
		if exclude_products_string:
			exclude_products.extend([entry.strip() for entry in exclude_products_string.split(",")])
		logger.info("List of excluded products: %s", exclude_products)
		products = self.service.execute_rpc("product_getObjects", [[], {"type": "LocalbootProduct", "id": include_products or None}])
		self.products = [entry.id for entry in products if entry.id not in exclude_products]
		self.products_with_only_uninstall = [
			entry.id
			for entry in products
			if entry.uninstallScript and
			not entry.setupScript and
			not entry.onceScript and
			not entry.customScript and
			not entry.updateScript and
			not entry.alwaysScript and
			not entry.userLoginScript and
			entry.id in self.products
		]
		logger.notice("Handling products %s", self.products)

	def set_single_action_request(self, product_on_client):
		if product_on_client.actionRequest not in (None, "none"):  # Could introduce --force to ignore/overwrite existing action Requests
			logger.debug(
				"Skipping %s %s as an actionRequest is set: %s",
				product_on_client.productId,
				product_on_client.clientId,
				product_on_client.actionRequest
			)
			return []  # existing actionRequests are left untouched

		if product_on_client.productId in self.depending_products:
			logger.info(
				"Setting '%s' ProductActionRequest with Dependencies: %s -> %s",
				self.request_type,
				product_on_client.productId,
				product_on_client.clientId
			)
			if not config.dry_run:
				self.service.execute_rpc(
					"setProductActionRequestWithDependencies",
					[product_on_client.productId, product_on_client.clientId, self.request_type]
				)
			return []  # no need to update the POC
		logger.info("Setting '%s' ProductActionRequest: %s -> %s", self.request_type, product_on_client.productId, product_on_client.clientId)
		if not config.dry_run:
			product_on_client.setActionRequest(self.request_type)
		return [product_on_client]

	def set_action_request(
		self,
		where_failed: bool = False,
		where_outdated: bool = False,
		uninstall_where_only_uninstall: bool = False
	) -> None:
		if config.dry_run:
			logger.notice("Operating in dry-run mode - not performing any actions")

		uninstall_products = []
		if uninstall_where_only_uninstall:
			uninstall_products = self.products_with_only_uninstall
			logger.notice("Uninstalling products (where installed): %s", uninstall_products)

		new_pocs = []
		pocs = self.service.execute_rpc(
			"productOnClient_getObjects",
			[[], {"clientId": self.clients or None, "productType": "LocalbootProduct", "productId": self.products}],
		)
		for entry in pocs:
			logger.debug("Checking %s (%s) on %s", entry.productId, entry.version, entry.clientId)
			try:
				available = self.depot_versions[self.client_to_depot[entry.clientId]][entry.productId]
			except KeyError:
				logger.error("Skipping check of %s %s (product not available on depot)", entry.clientId, entry.productId)
				continue
			if entry.productId in uninstall_products:
				logger.info("Setting 'uninstall' ProductActionRequest: %s -> %s", entry.productId, entry.clientId)
				if not config.dry_run:
					entry.setActionRequest("uninstall")
					new_pocs.append(entry)
			if where_failed and entry.actionResult == "failed":
				new_pocs.extend(self.set_single_action_request(entry))
			elif where_outdated and entry.version != available:
				new_pocs.extend(self.set_single_action_request(entry))
			# if neither where_failed nor where_outdated is set, set action request for every match
			elif not where_failed and not where_outdated:
				new_pocs.extend(self.set_single_action_request(entry))
		if not config.dry_run:
			logger.debug("Updating ProductOnClient")
			self.service.execute_rpc("productOnClient_updateObjects", [new_pocs])
