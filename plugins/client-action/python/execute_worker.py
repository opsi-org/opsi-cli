"""
opsi-cli basic command line interface for opsi

execute_worker
"""

from opsicommon.logging import get_logger

from opsicli.config import config
from opsicli.io import console_print
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
		with self.jsonrpc_mbus_connection.connection():
			results = self.jsonrpc_mbus_connection.jsonrpc(channels=channels, method="runOpsiScriptContent", params=(opsiscript,))
			for channel, result in results.items():
				if isinstance(result, Exception):
					logger.error("Error executing opsiscript on %s: %s", channel, result)
					continue

				exit_code = result.get("exit_code")
				stdout = result.get("stdout")
				stderr = result.get("stderr")
				log_content = result.get("log_content")

				if None in (exit_code, stdout, stderr, log_content):
					raise ValueError(f"Missing exit code, stdout, stderr or log content in result for channel {channel}")

				if stderr:
					raise RuntimeError(f"Opsiscript execution failed on {channel} with exit code {exit_code}: {stderr}")

				logger.info("Opsiscript executed on %s with exit code %d: %s", channel, exit_code, stdout)

				for content, label in [(stdout, "Standard Output"), (log_content, "Log Content")]:
					if content:
						console_print(f"===========  {label} for {channel}  ===========")
						console_print(content)
						console_print(f"===========  End of {label} for {channel}  ===========")

		return exit_code
