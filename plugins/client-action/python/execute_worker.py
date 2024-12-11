"""
opsi-cli basic command line interface for opsi

execute_worker
"""

import base64

from opsicommon.logging import get_logger

from opsicli.config import config
from opsicli.messagebus import JSONRPCMessagebusConnection, ProcessMessagebusConnection

from .client_action_worker import ClientActionArgs, ClientActionWorker

logger = get_logger("opsicli")


class ExecuteWorker(ClientActionWorker):
	def __init__(self, args: ClientActionArgs) -> None:
		super().__init__(args, default_all=False)
		self.mbus_connection = ProcessMessagebusConnection()
		self.jsonrpc_mbus_connection = JSONRPCMessagebusConnection()

	def execute(
		self,
		command: tuple[str],
		shell: bool = False,
		concurrent: int = 100,
		show_host_names: bool = True,
		timeout: float = 0.0,
		encoding: str = "auto",
		opsiscript: str | None = None,
	) -> int:
		if config.dry_run:
			logger.notice("Operating in dry-run mode - not performing any actions")
			return 0

		channels = [f"host:{client}" for client in self.clients]

		if opsiscript:
			return self._execute_opsiscript(channels, opsiscript)

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

	def _execute_opsiscript(self, channels: list[str], opsiscript: str) -> int:
		logger.debug("Executing opsiscript on %d hosts", len(channels))
		encoded_opsiscript = base64.b64encode(opsiscript.encode("utf-8")).decode("utf-8")

		with self.jsonrpc_mbus_connection.connection():
			results = self.jsonrpc_mbus_connection.jsonrpc(channels=channels, method="runOpsiScriptContent", params=(encoded_opsiscript,))
			for channel, result in results.items():
				if isinstance(result, Exception):
					logger.error("Error executing opsiscript on %s: %s", channel, result)
					raise result

				exit_code = result["exit_code"]
				if exit_code != 0:
					logger.error("Opsiscript execution failed on %s with exit code %d", channel, exit_code)
					return exit_code

				logger.info("Opsiscript executed on %s with exit code %d", channel, exit_code)

				log_content = result["log_content"]
				log_file_path = f"{channel.replace(':', '_')}_opsiscript.log"
				with open(log_file_path, "w", encoding="utf-8") as log_file:
					log_file.write(log_content)
				logger.info("Opsiscript log content for %s written to %s", channel, log_file_path)
		return 0
