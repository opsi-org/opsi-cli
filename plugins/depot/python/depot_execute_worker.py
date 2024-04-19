"""
opsi-cli basic command line interface for opsi

depot_execute_worker
"""

from opsicommon.logging import get_logger
from opsicommon.types import forceHostId

from opsicli.config import config
from opsicli.messagebus import ProcessMessagebusConnection
from opsicli.opsiservice import get_service_connection
from opsicli.types import OpsiCliRuntimeError

logger = get_logger("opsicli")


class NoDepotsSelected(OpsiCliRuntimeError):
	pass


class DepotExecuteWorker:
	def __init__(self, depots: str | None) -> None:
		self.service = get_service_connection()
		self.depots = self.determine_depots(depots)
		self.mbus_connection = ProcessMessagebusConnection()

	def determine_depots(self, depots: str | None) -> set[str]:
		result = set()
		depots = (depots or "").lower()
		if "all" in depots:
			result = {entry.id for entry in self.service.jsonrpc("host_getObjects", [[], {"type": "OpsiDepotserver"}])}
		elif depots:
			result.update(forceHostId(entry.strip()) for entry in depots.split(","))

		if not result:
			raise NoDepotsSelected("No depots selected")

		logger.notice("Selected depots: %s", result)
		return result

	def execute(
		self,
		command: tuple[str],
		shell: bool = False,
		concurrent: int = 100,
		show_host_names: bool = True,
		timeout: int = 0,
		encoding: str = "auto",
	) -> int:
		if config.dry_run:
			logger.notice("Operating in dry-run mode - not performing any actions")
			return 0

		channels = [f"service:depot:{depot}:process" for depot in self.depots]  # Should we use a different channel here?
		logger.debug("Executing %s with shell=%s on %d hosts", command, shell, len(channels))

		with self.mbus_connection.connection():
			return self.mbus_connection.execute_processes(
				channels=channels,
				command=command,
				shell=shell,
				concurrent=concurrent,
				show_host_names=show_host_names,
				timeout=timeout,
				encoding=encoding,
			)
