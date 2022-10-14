"""
opsi-cli basic command line interface for opsi

client_action_worker
"""

from typing import List

from opsicommon.logging import logger  # type: ignore[import]

from opsicli.opsiservice import get_service_connection


class ClientActionWorker:  # pylint: disable=too-many-instance-attributes
	def __init__(self, clients: str = None, client_groups: str = None, exclude_clients: str = None) -> None:
		self.service = get_service_connection()
		self.clients: List[str] = []
		self.determine_clients(clients, client_groups, exclude_clients)

	def client_ids_from_group(self, group: str):
		result = self.service.execute_rpc("group_getObjects", [[], {"id": group, "type": "HostGroup"}])
		if not result:
			raise ValueError(f"Client group '{group}' not found")
		return [mapping.objectId for mapping in self.service.execute_rpc("objectToGroup_getObjects", [[], {"groupId": result[0].id}])]

	def determine_clients(self, clients: str = None, client_groups: str = None, exclude_clients: str = None) -> None:
		if clients:
			self.clients = [entry.strip() for entry in clients.split(",")]
		else:
			self.clients = []
		if client_groups:
			for group in [entry.strip() for entry in client_groups.split(",")]:
				self.clients.extend(self.client_ids_from_group(group))
		if exclude_clients:
			self.clients = [entry for entry in self.clients if entry not in [exclude.strip() for exclude in exclude_clients.split(",")]]
		if not self.clients:
			raise ValueError("No clients selected")
		if "all" in self.clients:
			self.clients = []
		logger.notice("Selected clients: %s", self.clients or "all")
