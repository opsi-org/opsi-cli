"""
opsi-cli basic command line interface for opsi

client_action_worker
"""
from __future__ import annotations

from dataclasses import dataclass, field

from opsicommon.logging import get_logger

from opsicli.opsiservice import get_service_connection

logger = get_logger("opsicli")


@dataclass
class Group:
	name: str
	subgroups: list[Group] = field(default_factory=list)


@dataclass
class ClientActionArgs:
	clients: str | None = None
	client_groups: str | None = None
	exclude_clients: str | None = None
	exclude_client_groups: str | None = None
	only_online: bool = False


class ClientActionWorker:
	def __init__(self, args: ClientActionArgs) -> None:
		self.service = get_service_connection()
		self.clients: list[str] = []
		self.group_forest: dict[str, Group] = {}
		self.determine_clients(args)

	def create_group_forest(self) -> None:
		groups = self.service.jsonrpc("group_getObjects", [[], {"type": "HostGroup"}])
		for group in groups:
			self.group_forest[group["id"]] = Group(name=group["id"])
		for group in groups:
			if group["parentGroupId"]:
				self.group_forest[group["parentGroupId"]].subgroups.append(self.group_forest[group["id"]])

	def get_entries_from_group(self, group: str) -> set[str]:
		result = {mapping["objectId"] for mapping in self.service.jsonrpc("objectToGroup_getObjects", [[], {"groupId": group}])}
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

	def determine_clients(self, args: ClientActionArgs) -> None:
		self.clients = []
		if args.clients:
			self.clients.extend([entry.strip() for entry in args.clients.split(",")])
		if args.client_groups:
			for group in [entry.strip() for entry in args.client_groups.split(",")]:
				self.clients.extend(self.client_ids_from_group(group))
		if not args.clients and not args.client_groups or "all" in self.clients:  # select all clients
			self.clients = [entry["id"] for entry in self.service.jsonrpc("host_getObjects", [[], {"type": "OpsiClient"}])]
		exclude_clients_list = []
		if args.exclude_clients:
			exclude_clients_list = [exclude.strip() for exclude in args.exclude_clients.split(",")]
		if args.exclude_client_groups:
			for group in [entry.strip() for entry in args.exclude_client_groups.split(",")]:
				exclude_clients_list.extend(self.client_ids_from_group(group))
		self.clients = [entry for entry in self.clients if entry not in exclude_clients_list]
		if args.only_online:
			reachable = self.service.jsonrpc("host_getMessagebusConnectedIds")
			self.clients = [entry for entry in self.clients if entry in reachable]
		if not self.clients:
			raise ValueError("No clients selected")
		logger.notice("Selected clients: %s", self.clients)
