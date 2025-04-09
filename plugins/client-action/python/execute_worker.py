# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

execute_worker
"""

from opsicommon.logging import get_logger
from rich.text import Text

from opsicli.config import config
from opsicli.io import COLORS, LOG_COLORS, console_print
from opsicli.messagebus import JSONRPCMessagebusConnection, ProcessMessagebusConnection

from .client_action_worker import ClientActionArgs, ClientActionWorker

logger = get_logger("opsicli")


class ExecuteWorker(ClientActionWorker):
	def __init__(self, args: ClientActionArgs) -> None:
		super().__init__(args, default_all=False)
		self.mbus_connection = ProcessMessagebusConnection()
		self.jsonrpc_mbus_connection = JSONRPCMessagebusConnection()
		self.color_position = 0

	def execute(
		self,
		command: tuple[str],
		shell: bool = False,
		concurrent: int = 100,
		show_host_names: bool = True,
		timeout: float = 0.0,
		encoding: str = "auto",
		opsiscript: str | None = None,
		opsiscript_log_level: int = 0,
	) -> int:
		if config.dry_run:
			msg = "Operating in dry-run mode - not performing any actions"
			logger.notice(msg)
			console_print(msg + "\n", style="yellow")
			return 0

		channels = [f"host:{client}" for client in self.clients]

		if opsiscript:
			return self._execute_opsiscript(channels, opsiscript, opsiscript_log_level)

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

	def _execute_opsiscript(self, channels: list[str], opsiscript: str, opsiscript_log_level: int) -> int:
		logger.debug("Executing opsiscript on %d hosts", len(channels))
		highest_exit_code = 0

		with self.jsonrpc_mbus_connection.connection():
			results = self.jsonrpc_mbus_connection.jsonrpc(channels=channels, method="runOpsiScriptContent", params=(opsiscript,))

			for channel, result in results.items():
				host_name = channel.split(":")[1]
				line_prefix_color = COLORS[self.color_position]
				self.color_position = (self.color_position + 1) % len(COLORS)
				line_prefix = Text(f"{host_name} | ", style=line_prefix_color)
				console_print()
				console_print(rule=f"{host_name}", style="white")

				if isinstance(result, Exception):
					logger.error("Exception occured while executing opsiscript on %s: %s", channel, result)
					console_print(line_prefix + Text(str(result), style="red"))
					highest_exit_code = max(highest_exit_code, 1)
					continue

				if "error" in result:
					error_message = result["error"].get("message", "Unknown error")
					logger.error("Error occurred while executing opsiscript on %s: %s", channel, error_message)
					console_print(line_prefix + Text(error_message, style="red"))
					highest_exit_code = max(highest_exit_code, result["error"].get("code", 1))
					continue

				exit_code = result.get("exit_code", 1)
				highest_exit_code = max(highest_exit_code, exit_code)
				stdout = result.get("stdout")
				stderr = result.get("stderr")
				log_content = result.get("log_content")

				console_print(
					line_prefix
					+ Text("EXIT CODE: ", style="white")
					+ Text(
						f"{exit_code}",
						style="green" if exit_code == 0 else "red" if exit_code != 0 else "white",
					)
				)

				if stdout:
					console_print(Text("\n") + line_prefix + Text("STDOUT:", style="white"))
					for line in stdout.splitlines():
						console_print(line_prefix + Text(line, style="white"))

				if log_content:
					console_print(Text("\n") + line_prefix + Text("LOG:", style="white"))
					previous_color = "white"
					for line in log_content.splitlines():
						parts = line.split(" ", 1)
						log_level_value = int(parts[0].strip("[]"))
						if log_level_value <= opsiscript_log_level:
							color = LOG_COLORS.get(parts[0].strip("[]"), previous_color)
							previous_color = color
							console_print(line_prefix + Text(line, style=color))

				if stderr:
					console_print(Text("\n") + line_prefix + Text("STDERR:", style="white"))
					for line in str(stderr).splitlines():
						console_print(line_prefix + Text(line, style="red"))

		return highest_exit_code
