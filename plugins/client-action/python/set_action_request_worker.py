# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

client_action_worker
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Literal

from opsicommon.logging import get_logger
from opsicommon.objects import Product, ProductGroup, ProductOnClient, ProductOnDepot
from opsicommon.types import forceActionProgress, forceActionRequest, forceActionResult, forceInstallationStatus
from rich.text import Text

from opsicli.config import config
from opsicli.io import COLORS, Attribute, Metadata, OutputType, console_print, write_output

from .client_action_worker import ClientActionArgs, ClientActionWorker

STATIC_EXCLUDE_PRODUCTS = [
	"opsi-winst",
	"opsi-auto-update",
	"opsi-script",
	"shutdownwanted",
	"windows10-upgrade",
	"windows11-upgrade",
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


@dataclass
class SetActionRequestArgs:
	where_failed: bool = False
	where_outdated: bool = False
	where_installed: bool = False
	where_unknown: bool = False
	uninstall_where_only_uninstall: bool = False
	products: str | None = None
	exclude_products: str | None = None
	include_netboot: bool = False
	product_groups: str | None = None
	exclude_product_groups: str | None = None
	set_action_request: str = "setup"
	set_action_progress: str | None = None
	set_action_result: str | None = None
	set_installation_status: str | None = None
	setup_on_action: str | None = None
	process: bool = False
	process_visibility: Literal["visible", "hidden"] | None = None

	def __post_init__(self) -> None:
		if self.set_action_request is not None:
			self.set_action_request = forceActionRequest(self.set_action_request or "none")
		if self.set_action_progress is not None:
			self.set_action_progress = forceActionProgress(self.set_action_progress)
		if self.set_action_result is not None:
			self.set_action_result = forceActionResult(self.set_action_result or "none")
		if self.set_installation_status is not None:
			self.set_installation_status = forceInstallationStatus(self.set_installation_status)


class SetActionRequestWorker(ClientActionWorker):
	def __init__(self, args: ClientActionArgs) -> None:
		super().__init__(args)
		self.products: list[str] = []
		self.products_with_only_uninstall: list[str] = []
		self.depot_versions: dict[str, dict[str, str]] = {}
		self.product_action_scripts: dict[str, list[str]] = {}
		self.client_to_depot: dict[str, str] = {}

		for single_client_to_depot in self.service.jsonrpc("configState_getClientToDepotserver", [[], list(self.clients)]):
			self.client_to_depot[single_client_to_depot["clientId"]] = single_client_to_depot["depotId"]
		logger.trace("ClientToDepot mapping: %s", self.client_to_depot)

		product_on_depots: list[ProductOnDepot] = self.service.jsonrpc("productOnDepot_getObjects")
		for entry in product_on_depots:
			if not self.depot_versions.get(entry.depotId):
				self.depot_versions[entry.depotId] = {}
			self.depot_versions[entry.depotId][entry.productId] = f"{entry.productVersion}-{entry.packageVersion}"
		logger.trace("Product versions on depots: %s", self.depot_versions)

		products: list[Product] = self.service.jsonrpc("product_getObjects")
		for product in products:
			# store the available action request scripts (strip "Script" at the end of the property)
			self.product_action_scripts[product.id] = [key[:-6] for key in ACTION_REQUEST_SCRIPTS if getattr(product, key, None)]

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
		include_netboot: bool = False,
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
			"product_getObjects", [[], {"type": None if include_netboot else "LocalbootProduct", "id": products or None}]
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
		self,
		product_on_client: ProductOnClient,
		*,
		action_request: str | None = None,
		force: bool = False,
	) -> list[ProductOnClient]:
		"""
		Set the action request for a single ProductOnClient object.
		:param product_on_client: The ProductOnClient object to set the action request for.
		:param action_request: The action request to set. If None, the default action request is used.
		:param force: If True, the action request is set even if an existing action request is present.
		:return: The updated ProductOnClient objects.
		"""
		if not force and product_on_client.actionRequest not in (None, "none"):
			logger.info(
				"Skipping %s %s as an actionRequest is set: %s",
				product_on_client.productId,
				product_on_client.clientId,
				product_on_client.actionRequest,
			)
			# Existing actionRequests are left untouched
			if product_on_client.actionRequest != action_request:
				return []
			# If the actionRequest is the same as the one we want to set, return the object for further processing

		if (
			action_request
			and action_request.lower() != "none"
			and action_request not in self.product_action_scripts[product_on_client.productId]
		):
			logger.warning(
				"Skipping %s %s as the package does not have a script for: %s",
				product_on_client.productId,
				product_on_client.clientId,
				action_request,
			)
			return []

		logger.notice(
			"Setting action request for client %r, product %r to %r",
			product_on_client.clientId,
			product_on_client.productId,
			action_request,
		)

		# Remark: action_request="none" instead of None for compatibility with file backend
		product_on_client.actionRequest = action_request

		return [product_on_client]

	def set_action_requests_for_all(
		self,
		clients: Iterable[str],
		products: list[str],
		*,
		action_request: str | None = None,
		force: bool = False,
	) -> list[ProductOnClient]:
		"""
		Set the action request for all ProductOnClient objects for the given clients and products.
		:param clients: The clients to set the action request for.
		:param products: The products to set the action request for.
		:param action_request: The action request to set. If None, the default action request is used.
		:param force: If True, the action request is set even if an existing action request is present.
		:return: The updated ProductOnClient objects.
		"""
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
				new_pocs.extend(
					self.set_single_action_request(
						poc,
						action_request=action_request,
						force=force,
					)
				)
		return new_pocs

	def set_action_request(self, args: SetActionRequestArgs) -> None:
		self.determine_products(
			products_string=args.products,
			exclude_products_string=args.exclude_products,
			product_groups_string=args.product_groups,
			exclude_product_groups_string=args.exclude_product_groups,
			include_netboot=args.include_netboot,
			use_default_excludes=args.where_outdated or args.where_failed or args.where_installed or args.where_unknown,
		)
		if not self.products:
			raise ValueError("No product/s to set action request on. The specified product/s might not exist or might have been excluded.")

		if args.uninstall_where_only_uninstall:
			logger.notice("Uninstalling products (where installed): %s", self.products_with_only_uninstall)

		new_pocs: dict[str, dict[str, ProductOnClient]] = defaultdict(lambda: dict())
		if args.where_failed or args.where_outdated or args.where_installed or args.where_unknown or args.uninstall_where_only_uninstall:
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

				add_pocs = []
				if args.uninstall_where_only_uninstall and poc.productId in self.products_with_only_uninstall:
					add_pocs = self.set_single_action_request(poc, action_request="uninstall", force=True)
				elif args.where_failed and poc.actionResult == "failed":
					add_pocs = self.set_single_action_request(poc, action_request=args.set_action_request, force=True)
				elif args.where_installed and poc.installationStatus == "installed":
					add_pocs = self.set_single_action_request(poc, action_request=args.set_action_request, force=True)
				elif args.where_unknown and poc.installationStatus == "unknown" and poc.actionRequest not in ("setup","uninstall","once", "update"):
					add_pocs = self.set_single_action_request(poc, action_request=args.set_action_request, force=True)
				elif (
					args.where_outdated
					and poc.installationStatus == "installed"
					and f"{poc.productVersion}-{poc.packageVersion}" != available
				):
					add_pocs = self.set_single_action_request(poc, action_request=args.set_action_request)
				for add_poc in add_pocs:
					new_pocs[add_poc.clientId][add_poc.productId] = add_poc

			modified_clients = list(new_pocs)
			if args.setup_on_action and modified_clients:
				setup_on_action_products = [entry.strip() for entry in args.setup_on_action.split(",")]
				logger.notice("Setting setup for all modified clients and products: %s", setup_on_action_products)
				for add_poc in self.set_action_requests_for_all(
					modified_clients, setup_on_action_products, action_request="setup", force=True
				):
					if add_poc.productId not in new_pocs[add_poc.clientId]:
						new_pocs[add_poc.clientId][add_poc.productId] = add_poc

		# If neither where_failed nor where_outdated nor uninstall_where_only_uninstall is set, set action request for every selected client
		else:
			if not args.products and not args.product_groups:
				raise ValueError("When unconditionally setting actionRequests, you must supply --products or --product-groups.")
			for add_poc in self.set_action_requests_for_all(
				self.clients, self.products, action_request=args.set_action_request, force=True
			):
				new_pocs[add_poc.clientId][add_poc.productId] = add_poc

		if not new_pocs:
			msg = "No action requests to set."
			logger.notice(msg)
			console_print(f"{msg}\n", output_type=OutputType.MESSAGE)
			return

		update_pocs: list[ProductOnClient] = []
		for client_id in sorted(new_pocs):
			for product_id in sorted(new_pocs[client_id]):
				update_pocs.append(new_pocs[client_id][product_id])

		logger.trace("New ProductOnClient objects to update: %s", update_pocs)

		logger.debug("Adding dependent product actions")
		update_pocs = self.service.jsonrpc("productOnClient_addDependencies", [update_pocs])
		logger.trace("New ProductOnClient objects to update with added dependencies: %s", update_pocs)

		if args.set_action_progress is not None or args.set_action_result is not None or args.set_installation_status is not None:
			for product_on_client in update_pocs:
				if args.set_action_progress is not None:
					product_on_client.setActionProgress(args.set_action_progress)
				if args.set_action_result is not None:
					product_on_client.setActionResult(args.set_action_result)
				if args.set_installation_status is not None:
					product_on_client.setInstallationStatus(args.set_installation_status)

		if not config.dry_run:
			logger.debug("Updating ProductOnClient objects")
			self.service.jsonrpc("productOnClient_updateObjects", [update_pocs])

		msg = f"Action requests {'would ' if config.dry_run else ''}have been set"
		if args.process:
			msg += f" and processing {'would have been started' if config.dry_run else 'was started'}"
			if not config.dry_run:
				logger.debug("Processing action requests")
				for client_id, pocs_by_product in new_pocs.items():
					res = self.service.jsonrpc(
						"hostControl_processActionRequests",
						[[client_id], list(pocs_by_product), args.process_visibility],
						read_timeout=60,
					)
					logger.debug("Result of hostControl_processActionRequests: %s", res)

		console_print(f"{msg}. Here are the updated ProductOnClient objects:\n", style="green", output_type=OutputType.MESSAGE)

		metadata = Metadata(
			attributes=[
				Attribute(id="clientId", description="ID of the client", identifier=True, data_type="str"),
				Attribute(id="productId", description="ID of the product", identifier=True, data_type="str"),
				Attribute(id="actionRequest", description="Product action request set", data_type="str"),
				Attribute(id="actionProgress", description="Product action progress", data_type="str", selected=False),
				Attribute(id="actionResult", description="Product action result", data_type="str", selected=False),
				Attribute(id="installationStatus", description="Product installation status", data_type="str", selected=False),
			]
		)
		write_output(
			data=[
				{
					"clientId": poc.clientId,
					"productId": poc.productId,
					"actionRequest": poc.actionRequest,
					"actionProgress": poc.actionProgress,
					"actionResult": poc.actionResult,
					"installationStatus": poc.installationStatus,
				}
				for poc in update_pocs
			],
			metadata=metadata,
		)

	def process_actions(self, args: SetActionRequestArgs) -> None:
		self.determine_products(
			products_string=args.products,
			exclude_products_string=args.exclude_products,
			product_groups_string=args.product_groups,
			exclude_product_groups_string=args.exclude_product_groups,
			use_default_excludes=True,
		)
		if not self.products:
			raise ValueError("No products to process. The specified products might not exist or might have been excluded.")

		if config.dry_run:
			console_print(
				f"Process actions skipped: would process action requests for {len(self.clients)} clients"
				+ (f" and products: {len(self.products)}" if self.products else "")
				+ (f" with visibility: {args.process_visibility}" if args.process_visibility else ""),
				output_type=OutputType.WARNING_MESSAGE,
			)
			return

		result = self.service.jsonrpc(
			"hostControl_processActionRequests",
			[list(self.clients), self.products, args.process_visibility],
			read_timeout=60,
		)
		logger.debug(f"Result of hostControl_processActionRequests: {result}")

		color_position = 0
		for client, data in result.items():
			client_color = COLORS[color_position]
			color_position = (color_position + 1) % len(COLORS)
			line_prefix = Text(f"{client} | ", style=client_color)

			if isinstance(data, dict):
				error = data.get("error")
				result_value = data.get("result")
				if error:
					console_print(
						line_prefix + Text(str(error), style="red"),
						output_type=OutputType.DATA,
					)
				elif result_value is not None:
					console_print(
						line_prefix + Text(str(result_value), style="white"),
						output_type=OutputType.DATA,
					)
			else:
				console_print(
					line_prefix + Text(f"Unexpected response: {data}", style="yellow"),
					output_type=OutputType.WARNING_MESSAGE,
				)
