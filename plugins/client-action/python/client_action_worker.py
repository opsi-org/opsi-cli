"""
opsi-cli basic command line interface for opsi

client_action_worker
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from ipaddress import ip_network

from opsicommon.logging import get_logger
from opsicommon.objects import Group as GroupObject
from opsicommon.objects import ObjectToGroup, OpsiClient
from opsicommon.types import forceHostId
from opsicommon.utils import ip_address_in_network

from opsicli.io import get_console
from opsicli.opsiservice import get_service_connection
from opsicli.types import OpsiCliRuntimeError

logger = get_logger("opsicli")


@dataclass
class Group:
	name: str
	subgroups: list[Group] = field(default_factory=list)


@dataclass
class ClientActionArgs:
	clients: str | None = None
	client_groups: str | None = None
	clients_from_depots: str | None = None
	ip_addresses: str | None = None
	exclude_clients: str | None = None
	exclude_client_groups: str | None = None
	exclude_ip_addresses: str | None = None
	only_online: bool = False


class NoClientsSelected(OpsiCliRuntimeError):
	pass


class ClientActionWorker:
	def __init__(self, args: ClientActionArgs, default_all: bool = True) -> None:
		self.service = get_service_connection()
		self.clients: set[str] = set()
		self.group_forest: dict[str, Group] = {}
		self.default_all = default_all
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
		obj_to_groups: list[ObjectToGroup] = self.service.jsonrpc("objectToGroup_getObjects", [[], {"groupId": group}])
		result = {obj_to_group.objectId for obj_to_group in obj_to_groups}
		logger.debug("group %s has clients: %s", group, result)
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
		return [entry.clientId for entry in self.service.jsonrpc("configState_getClientToDepotserver", [depot])]

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
		args.clients = (args.clients or "").lower()
		if not args.clients and not args.client_groups and not args.ip_addresses and not args.clients_from_depots and self.default_all:
			console = get_console(file=sys.stderr)
			console.print(
				"[bright_yellow]No clients selected, defaulting to all clients.\n"
				"This is deprecated, please use `--clients all` to select all clients.[/bright_yellow]"
			)
			args.clients = "all"
		if "all" in args.clients:
			clients: list[OpsiClient] = self.service.jsonrpc("host_getObjects", [[], {"type": "OpsiClient"}])
			self.clients = {entry.id for entry in clients}
		else:
			if args.clients:
				self.clients.update(forceHostId(entry.strip()) for entry in args.clients.split(","))
			if args.client_groups:
				for group in [entry.strip() for entry in args.client_groups.split(",")]:
					self.clients.update(self.client_ids_from_group(group))
			if args.ip_addresses:
				for ip_address in args.ip_addresses.split(","):
					self.clients.update(self.client_ids_with_ip(ip_address))
			if args.clients_from_depots:
				for depot in args.clients_from_depots.split(","):
					self.clients.update(self.client_ids_from_depot(depot))

		exclude_clients = set()
		if args.exclude_clients:
			exclude_clients = {forceHostId(exclude.strip()) for exclude in args.exclude_clients.split(",")}
		if args.exclude_client_groups:
			for group in [entry.strip() for entry in args.exclude_client_groups.split(",")]:
				exclude_clients.update(self.client_ids_from_group(group))
		if args.exclude_ip_addresses:
			for ip_address in args.exclude_ip_addresses.split(","):
				exclude_clients.update(self.client_ids_with_ip(ip_address.strip()))
		self.clients -= exclude_clients
		if args.only_online:
			reachable = set(self.service.jsonrpc("host_getMessagebusConnectedIds"))
			self.clients.intersection_update(reachable)

		if not self.clients:
			raise NoClientsSelected("No clients selected")

		logger.notice("Selected clients: %s", self.clients)
