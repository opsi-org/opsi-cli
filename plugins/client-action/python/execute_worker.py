"""
opsi-cli basic command line interface for opsi

execute_worker
"""

from opsicommon.logging import get_logger

from opsicli.config import config
from opsicli.messagebus import ProcessMessagebusConnection

from .client_action_worker import ClientActionArgs, ClientActionWorker

logger = get_logger("opsicli")


class ExecuteWorker(ClientActionWorker):
	def __init__(self, args: ClientActionArgs) -> None:
		super().__init__(args)
		self.mbus_connection = ProcessMessagebusConnection()

	def execute(
		self, command: tuple[str], shell: bool = False, show_host_names: bool = False, timeout: float | None = None, encoding: str = "auto"
	) -> int:
		if config.dry_run:
			logger.notice("Operating in dry-run mode - not performing any actions")
			return 0

		channels = [f"host:{client}" for client in self.clients]
		logger.debug("Executing %s with shell=%s on %d hosts", command, shell, len(channels))

		with self.mbus_connection.connection():
			return self.mbus_connection.execute_processes(
				channels=channels, command=command, shell=shell, show_host_names=show_host_names, timeout=timeout, encoding=encoding
			)
