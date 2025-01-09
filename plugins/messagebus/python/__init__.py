"""
opsi-cli basic command line interface for opsi

messagebus plugin
"""

import sys
from threading import Event
from typing import Any

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger
from opsicommon.messagebus.message import EventMessage

from opsicli.messagebus import MessagebusConnection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.3.0"
__description__ = "This command can be used to interact with the opsi message bus."

logger = get_logger("opsicli")


class WaitForEventMessagebusConnection(MessagebusConnection):
	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self.wait_for_type: str | None = None
		self.wait_for_data: list[dict[str, Any]] | None = None
		self.event_found_event = Event()  # why does everything have be named event?
		self.result: EventMessage | None = None

	def _on_event(self, message: EventMessage) -> None:
		if self.wait_for_type and message.event != self.wait_for_type:
			logger.debug("Found event of different type %s", message.event)
			return
		if self.wait_for_data:
			for data in self.wait_for_data:
				for key, value in data.items():
					if message.data.get(key) != value:
						break
				else:  # all key-value pairs matched
					logger.notice("Received requested event %s (data=%s)", message, message.data)
					self.result = message
					self.event_found_event.set()
					return
			logger.debug("Found event with different data %s", message.data)
		else:
			logger.notice("Received requested event %s (data=%s)", message, message.data)
			self.result = message
			self.event_found_event.set()

	def wait_for_event(
		self, type: str | None = None, data: list[dict[str, Any]] | None = None, timeout: float | None = None
	) -> EventMessage:
		self.wait_for_type = type
		self.wait_for_data = data
		logger.notice("Waiting for event of type %r with data %s to occur", self.wait_for_type, self.wait_for_data)
		try:
			with self.connection():
				self.subscribe_to_channel(f"event:{self.wait_for_type}")
				self.event_found_event.wait(timeout)
				if not self.result:
					logger.error("Something went wrong - no matching event received")
					raise RuntimeError("No matching event received")
				return self.result
		finally:
			self.result = None
			self.event_found_event.clear()


@click.group(name="messagebus", short_help="Command group to interact with opsi messagebus")
@click.version_option(__version__, message="opsi-cli plugin messagebus, version %(version)s")
def cli() -> None:
	"""
	This command can be used to interact with opsi messagebus.
	"""
	logger.trace("messagebus command group")


@cli.command(name="wait-for-event", short_help="Wait for a specific event on the messagebus")
@click.argument("type", type=str)
@click.option("--data", help="Data of the event to wait for", type=str, multiple=True)
@click.option("--timeout", help="Timeout in seconds", type=float, default=None)
def wait_for_event(type: str, data: list[str], timeout: float | None) -> None:
	"""
	opsi-cli messagebus wait-for-event command
	"""
	mbus_connection = WaitForEventMessagebusConnection()
	data_list: list[dict[str, Any]] | None = None
	if data:
		data_list = [{entry[0].strip(): entry[1].strip() for entry in [assignment.split("=", 1) for assignment in data]}]
	result = mbus_connection.wait_for_event(type=type, data=data_list, timeout=timeout)
	print(result.data)


@cli.command(name="wait-for-installation", short_help="Wait for a a product installation on a client")
@click.argument("client", type=str)
@click.argument("product", type=str)
@click.argument("installation-status", type=str)
@click.option("--timeout", help="Timeout in seconds", type=float, default=None)
def wait_for_installation(client: str, product: str, installation_status: str, timeout: float | None) -> None:
	"""
	opsi-cli messagebus wait-for-installation command
	"""
	mbus_connection = WaitForEventMessagebusConnection()
	wait_for_data = [
		{"clientId": client, "productId": product, "actionRequest": "none", "installationStatus": installation_status},
		{"clientId": client, "productId": product, "actionRequest": "none", "installationStatus": "unknown"},
	]
	result = mbus_connection.wait_for_event(type="productOnClient_updated", data=wait_for_data, timeout=timeout)
	print(result.data)
	if result.data.get("installation_status") == "unknown":
		logger.error("Installation failed")
		sys.exit(1)


# This class keeps track of the plugins meta-information
class MessagebusPlugin(OPSICLIPlugin):
	name: str = "Messagebus"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
