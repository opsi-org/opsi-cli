"""
opsi-cli basic command line interface for opsi

client_action_worker
"""

from typing import List

from opsicommon.logging import logger  # type: ignore[import]

from opsicli.opsiservice import get_service_connection


class ClientActionWorker:  # pylint: disable=too-many-instance-attributes
	def __init__(
		self, clients: str = None, client_groups: str = None, exclude_clients: str = None, exclude_client_groups: str = None
	) -> None:
		self.service = get_service_connection()
		self.clients: List[str] = []
		self.determine_clients(clients, client_groups, exclude_clients, exclude_client_groups)

	def client_ids_from_group(self, group: str):
		result = self.service.execute_rpc("group_getObjects", [[], {"id": group, "type": "HostGroup"}])
		if not result:
			raise ValueError(f"Client group '{group}' not found")
		return [mapping.objectId for mapping in self.service.execute_rpc("objectToGroup_getObjects", [[], {"groupId": result[0].id}])]

	def determine_clients(
		self, clients: str = None, client_groups: str = None, exclude_clients: str = None, exclude_client_groups: str = None
	) -> None:
		self.clients = []
		if not clients and not client_groups:  # select all clients
			self.clients = [entry.id for entry in self.service.execute_rpc("host_getObjects", [[], {"type": "OpsiClient"}])]
		if clients:
			self.clients.extend([entry.strip() for entry in clients.split(",")])
		if client_groups:
			for group in [entry.strip() for entry in client_groups.split(",")]:
				self.clients.extend(self.client_ids_from_group(group))
		exclude_clients_list = []
		if exclude_clients:
			exclude_clients_list = [exclude.strip() for exclude in exclude_clients.split(",")]
		if exclude_client_groups:
			for group in [entry.strip() for entry in exclude_client_groups.split(",")]:
				exclude_clients_list.extend(self.client_ids_from_group(group))
		self.clients = [entry for entry in self.clients if entry not in exclude_clients_list]
		if not self.clients:
			raise ValueError("No clients selected")
		logger.notice("Selected clients: %s", self.clients)