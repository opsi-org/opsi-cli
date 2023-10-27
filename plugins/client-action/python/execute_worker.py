"""
opsi-cli basic command line interface for opsi

execute_worker
"""

import sys
from typing import Any

from opsicommon.logging import get_logger

from opsicli.config import config
from opsicli.io import get_console
from opsicli.messagebus import JSONRPCMessagebusConnection

from .client_action_worker import ClientActionArgs, ClientActionWorker

logger = get_logger("opsicli")
console = get_console()

# Alternative Idea: work with Terminals derived from TerminalMessagebusConnection


def print_output(data: Any, descriptor: str = "result") -> None:
	if isinstance(data, list):
		lines = data
	else:
		lines = str(data).splitlines()
	if len(lines) > 1 and not lines[-1]:
		del lines[-1]  # strip empty line at end
	result = "\n".join((f"[purple]{descriptor}[/purple]: {line}" for line in lines))
	console.print(result)


class ExecuteWorker(ClientActionWorker):
	def __init__(self, args: ClientActionArgs) -> None:
		super().__init__(args)
		self.mbus_connection = JSONRPCMessagebusConnection()

	def execute(self, command: list[str]) -> None:
		if config.dry_run:
			logger.notice("Operating in dry-run mode - not performing any actions")
			return

		cmd = (command, True, True, "utf-8", 60)
		channels = [f"host:{client}" for client in self.clients]
		fails: list[str] = []
		with self.mbus_connection.connection():
			results = self.mbus_connection.jsonrpc(channels, "execute", cmd)
		for channel, result in results.items():
			output = result
			if isinstance(result, dict) and (result.get("code") != 0 or "Error" in result.get("data", {}).get("class")):
				fails.append(channel[5:])
				output = f"Error: {result.get('message')}"
			print_output(output, descriptor=channel[5:])
		if fails:
			logger.error("Command failed on hosts %r", fails)
			sys.exit(1)
