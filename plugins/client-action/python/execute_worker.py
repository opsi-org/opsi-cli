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
		highest_exit_code = 0
		with self.jsonrpc_mbus_connection.connection():
			results = self.jsonrpc_mbus_connection.jsonrpc(channels=channels, method="runOpsiScriptContent", params=(opsiscript,))
			console_print("=========== EXECUTION SUMMARY ===========")
			for channel, result in results.items():
				if isinstance(result, Exception):
					logger.error("Error executing opsiscript on %s: %s", channel, result)
					highest_exit_code = max(highest_exit_code, 1)
					continue

				exit_code = result.get("exit_code")
				highest_exit_code = max(highest_exit_code, exit_code)
				stdout = result.get("stdout")
				stderr = result.get("stderr")
				log_content = result.get("log_content")

				if None in (exit_code, stdout, stderr, log_content):
					raise ValueError(f"Missing exit code, stdout, stderr or log content in result for channel {channel}")

				console_print(f"{channel}	| EXIT CODE: {exit_code}")

				if stdout:
					console_print(f"{channel}	| OUTPUT:")
					for line in stdout.splitlines():
						console_print(f"{channel}	| {line}")

				if log_content:
					console_print(f"{channel}	| LOG:")
					for line in log_content.splitlines():
						console_print(f"{channel}	| {line}")

				if stderr:
					console_print(f"{channel}	| ERROR:")
					for line in stderr.splitlines():
						console_print(f"{channel}	| {line}")

				console_print("-----------------------------------------")
			console_print("=========================================")

		return highest_exit_code
