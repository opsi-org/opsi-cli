# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

execute_worker
"""

from pathlib import Path

from opsicommon.logging import get_logger
from rich.text import Text

from opsicli.config import config
from opsicli.io import COLORS, LOG_COLORS, OutputType, console_print
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
			logger.notice("Execution skipped, returning exit code 0.")
			console_print(
				f"Execution skipped: would execute command on {len(self.clients)} clients. Returning exit code 0.",
				output_type=OutputType.WARNING_MESSAGE,
			)
			return 0

		channels = [f"host:{client}" for client in self.clients]

		if opsiscript:
			if "\n" not in opsiscript and Path(opsiscript).is_file():
				return self._execute_opsiscript(channels, Path(opsiscript).read_text(encoding="utf-8"), opsiscript_log_level)
			else:
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
				line_prefix_color = COLORS[self.color_position] if config.color else ""
				self.color_position = (self.color_position + 1) % len(COLORS)
				line_prefix = Text(f"{host_name} | ", style=line_prefix_color)
				console_print(output_type=OutputType.DATA)
				console_print(rule=f"{host_name}", output_type=OutputType.DATA)

				if isinstance(result, Exception):
					logger.error("Exception occured while executing opsiscript on %s: %s", channel, result)
					console_print(line_prefix + Text(str(result), style="red" if config.color else None), output_type=OutputType.DATA)
					highest_exit_code = max(highest_exit_code, 1)
					continue

				if "error" in result:
					error_message = result["error"].get("message", "Unknown error")
					logger.error("Error occurred while executing opsiscript on %s: %s", channel, error_message)
					console_print(line_prefix + Text(error_message, style="red" if config.color else None), output_type=OutputType.DATA)
					highest_exit_code = max(highest_exit_code, result["error"].get("code", 1))
					continue

				exit_code = result.get("exit_code", 1)
				highest_exit_code = max(highest_exit_code, exit_code)
				stdout = result.get("stdout")
				stderr = result.get("stderr")
				log_content = result.get("log_content")

				console_print(
					line_prefix
					+ Text("EXIT CODE: ")
					+ Text(
						f"{exit_code}",
						style="" if not config.color else ("green" if exit_code == 0 else "red"),
					),
					output_type=OutputType.DATA,
				)

				if stdout:
					console_print(Text("\n") + line_prefix + Text("STDOUT:"), output_type=OutputType.DATA)
					for line in stdout.splitlines():
						console_print(line_prefix + Text(line), output_type=OutputType.DATA)

				if log_content:
					console_print(Text("\n") + line_prefix + Text("LOG:"), output_type=OutputType.DATA)
					previous_color = "white"
					for line in log_content.splitlines():
						parts = line.split(" ", 1)
						try:
							log_level_value = int(parts[0].strip("[]"))
						except ValueError:  # invalid stuff in brackets
							log_level_value = 0  # assume multiline entry
						if log_level_value <= opsiscript_log_level:
							color = LOG_COLORS.get(parts[0].strip("[]"), previous_color)
							previous_color = color
							console_print(line_prefix + Text(line, style=color), output_type=OutputType.DATA)

				if stderr:
					console_print(Text("\n") + line_prefix + Text("STDERR:"), output_type=OutputType.DATA)
					for line in str(stderr).splitlines():
						console_print(line_prefix + Text(line, style="red"), output_type=OutputType.DATA)

		return highest_exit_code
