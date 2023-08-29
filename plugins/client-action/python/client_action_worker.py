"""
opsi-cli basic command line interface for opsi

client_action_worker
"""

from dataclasses import dataclass

from opsicommon.logging import get_logger

from opsicli.opsiservice import get_service_connection

logger = get_logger("opsicli")


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
		self.determine_clients(args)

	def client_ids_from_group(self, group: str) -> list[str]:
		result = self.service.jsonrpc("group_getObjects", [[], {"id": group, "type": "HostGroup"}])
		if not result:
			raise ValueError(f"Client group '{group}' not found")
		return [mapping["objectId"] for mapping in self.service.jsonrpc("objectToGroup_getObjects", [[], {"groupId": result[0]["id"]}])]

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
