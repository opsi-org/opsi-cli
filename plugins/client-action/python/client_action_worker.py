# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

client_action_worker
"""

from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import ip_network

from opsicommon.logging import get_logger
from opsicommon.objects import Group as GroupObject
from opsicommon.objects import ObjectToGroup, OpsiClient
from opsicommon.types import forceActionRequest, forceGroupId, forceHostId, forceIPAddress
from opsicommon.utils import ip_address_in_network

from opsicli.io import deprecation_warning
from opsicli.opsiservice import get_service_connection
from opsicli.types import OpsiCliRuntimeError

logger = get_logger("opsicli")


@dataclass
class Group:
	name: str
	subgroups: list[Group] = field(default_factory=list)


class ClientActionArgs:
	def __init__(
		self,
		clients: str | None = None,
		client_groups: str | None = None,
		clients_from_depots: str | None = None,
		ip_addresses: str | None = None,
		exclude_clients: str | None = None,
		exclude_client_groups: str | None = None,
		exclude_ip_addresses: str | None = None,
		where_action_request: str | None = None,
		only_online: bool = False,
	) -> None:
		self.clients: set[str] = {
			"all" if client.strip().lower() == "all" else forceHostId(client.strip())
			for client in (clients or "").split(",")
			if client.strip()
		}
		self.client_groups: set[str] = {forceGroupId(group.strip()) for group in (client_groups or "").split(",") if group.strip()}
		self.clients_from_depots: set[str] = {
			forceHostId(depot.strip()) for depot in (clients_from_depots or "").split(",") if depot.strip()
		}
		self.ip_addresses: set[str] = {forceIPAddress(ip.strip()) for ip in (ip_addresses or "").split(",") if ip.strip()}
		self.exclude_clients: set[str] = {forceHostId(client.strip()) for client in (exclude_clients or "").split(",") if client.strip()}
		self.exclude_client_groups: set[str] = {
			forceGroupId(group.strip()) for group in (exclude_client_groups or "").split(",") if group.strip()
		}
		self.exclude_ip_addresses: set[str] = {forceIPAddress(ip.strip()) for ip in (exclude_ip_addresses or "").split(",") if ip.strip()}
		self.where_action_request: set[str] = {
			forceActionRequest(request.strip()) for request in (where_action_request or "").split(",") if request.strip()
		}
		self.only_online: bool = only_online


class NoClientsSelected(OpsiCliRuntimeError):
	pass


class NoClientsOnline(OpsiCliRuntimeError):
	pass


class ClientActionWorker:
	def __init__(self, args: ClientActionArgs, default_all: bool = True, error_if_no_clients_online: bool = True) -> None:
		self.service = get_service_connection()
		self.clients: set[str] = set()
		self.group_forest: dict[str, Group] = {}
		self.default_all = default_all
		self.error_if_no_clients_online = error_if_no_clients_online
		self.determine_clients(args)

	def create_group_forest(self) -> None:
		groups: list[GroupObject] = self.service.jsonrpc("group_getObjects", [[], {"type": "HostGroup"}])
		for group in groups:
			self.group_forest[group.id] = Group(name=group.id)
		for group in groups:
			if group.parentGroupId and group.parentGroupId != "null":
				try:
					self.group_forest[group.parentGroupId].subgroups.append(self.group_forest[group.id])
				except KeyError:
					logger.error("Error in Backend: Group %s has parent %s which does not exist", group.id, group.parentGroupId)

	def get_entries_from_group(self, group: str) -> set[str]:
		if group not in self.group_forest:
			raise ValueError(f"Group {group!r} not found")
		obj_to_groups: list[ObjectToGroup] = self.service.jsonrpc("objectToGroup_getObjects", [[], {"groupId": group}])
		result = {obj_to_group.objectId for obj_to_group in obj_to_groups}
		logger.debug("Group %s has clients: %s", group, result)
		if self.group_forest[group].subgroups:
			for subgroup in self.group_forest[group].subgroups:
				sub_result = self.get_entries_from_group(subgroup.name)
				result = result.union(sub_result)
		return result

	def client_ids_from_group(self, group: str) -> list[str]:
		if not self.group_forest:
			self.create_group_forest()
		return list(self.get_entries_from_group(group))

	def client_ids_from_depot(self, depot: str) -> list[str]:
		return [entry["clientId"] for entry in self.service.jsonrpc("configState_getClientToDepotserver", [depot])]

	def client_ids_with_ip(self, ip_string: str) -> list[str]:
		network = ip_network(ip_string)  # can handle ipv4 and ipv6 addresses with and without subnet specification
		result = []
		clients: list[OpsiClient] = self.service.jsonrpc("host_getObjects", [[], {"type": "OpsiClient"}])
		for client in clients:
			if client.ipAddress and ip_address_in_network(client.ipAddress, network):
				result.append(client.id)
		logger.debug("Clients with ip %s: %s", ip_string, result)
		return result

	def determine_clients(self, args: ClientActionArgs) -> None:
		self.clients = set()
		all_clients: set[str] = {client.id for client in self.service.jsonrpc("host_getObjects", [[], {"type": "OpsiClient"}])}

		if not args.clients and not args.client_groups and not args.ip_addresses and not args.clients_from_depots and self.default_all:
			deprecation_warning(
				"No clients selected, defaulting to all clients.\nThis is deprecated, please use `--clients all` to select all clients.\n"
			)
			args.clients = {"all"}
		if "all" in args.clients:
			self.clients = all_clients
		else:
			if args.clients:
				clients_not_found = args.clients - all_clients
				if clients_not_found:
					raise ValueError(f"Clients not found: {clients_not_found}")
				self.clients.update(args.clients)
			if args.client_groups:
				for group in args.client_groups:
					self.clients.update(self.client_ids_from_group(group))
			if args.ip_addresses:
				for ip_address in args.ip_addresses:
					self.clients.update(self.client_ids_with_ip(ip_address))
			if args.clients_from_depots:
				for depot in args.clients_from_depots:
					self.clients.update(self.client_ids_from_depot(depot))

		if args.where_action_request:
			self.clients = {
				poc[2]
				for poc in self.service.jsonrpc(
					"productOnClient_getIdents",
					["tuple", {"clientId": list(self.clients), "actionRequest": list(args.where_action_request)}],
				)
			}

		exclude_clients = set()
		if args.exclude_clients:
			exclude_clients = args.exclude_clients
		if args.exclude_client_groups:
			for group in args.exclude_client_groups:
				exclude_clients.update(self.client_ids_from_group(group))
		if args.exclude_ip_addresses:
			for ip_address in args.exclude_ip_addresses:
				exclude_clients.update(self.client_ids_with_ip(ip_address))
		self.clients -= exclude_clients

		if not self.clients:
			raise NoClientsSelected("No clients selected")

		if args.only_online:
			reachable = set(self.service.jsonrpc("host_getMessagebusConnectedIds"))
			self.clients.intersection_update(reachable)

		if not self.clients and self.error_if_no_clients_online:
			raise NoClientsOnline("No clients online")

		logger.notice("Selected clients: %s", self.clients)
