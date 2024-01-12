"""
opsi-cli basic command line interface for opsi

execute_worker
"""

import sys

from opsicommon.logging import get_logger
from opsicommon.messagebus import ProcessDataReadMessage, ProcessErrorMessage, ProcessStopEventMessage

from opsicli.config import config
from opsicli.io import get_console
from opsicli.messagebus import ProcessMessagebusConnection

from .client_action_worker import ClientActionArgs, ClientActionWorker

logger = get_logger("opsicli")
console = get_console()


def print_output(data: list[str], descriptor: str = "result") -> None:
	lines = "\n".join(data).splitlines()
	if len(lines) > 1 and not lines[-1]:
		del lines[-1]  # strip empty line at end
	result = "\n".join((f"[purple]{descriptor}[/purple]: {line}" for line in lines))
	console.print(result)


class ExecuteWorker(ClientActionWorker):
	def __init__(self, args: ClientActionArgs) -> None:
		super().__init__(args)
		self.mbus_connection = ProcessMessagebusConnection()

	def execute(self, command: tuple[str], timeout: float | None = None) -> None:
		if config.dry_run:
			logger.notice("Operating in dry-run mode - not performing any actions")
			return

		channels = [f"host:{client}" for client in self.clients]
		fails: list[str] = []
		with self.mbus_connection.connection():
			results = self.mbus_connection.execute_processes(channels, command, timeout=timeout)
		for channel, result in results.items():
			output = []
			for message in result:
				if isinstance(message, ProcessDataReadMessage):
					if message.stdout:
						output.append(message.stdout.decode("utf-8"))
					if message.stderr:
						output.append(message.stderr.decode("utf-8"))
				elif isinstance(message, ProcessStopEventMessage):
					if message.exit_code != 0:
						if channel[5:] not in fails:
							fails.append(channel[5:])
				elif isinstance(message, ProcessErrorMessage):
					output.append(f"Error {message.error.code}: {message.error.message}")  # could use data['details']
					if channel[5:] not in fails:
						fails.append(channel[5:])
				elif isinstance(message, Exception):
					if channel[5:] not in fails:
						output.append(f"Error: {message}")
						fails.append(channel[5:])
			print_output(output, descriptor=channel[5:])
		if fails:
			logger.error("Command failed on hosts %r", fails)
			sys.exit(1)
