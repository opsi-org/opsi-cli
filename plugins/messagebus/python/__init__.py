# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

messagebus plugin
"""

import sys
import time
from threading import Event
from typing import Any, Literal

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.messagebus.message import EventMessage

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.decorators import dry_run_handling
from opsicli.io import write_output
from opsicli.messagebus import MessagebusConnection
from opsicli.plugin import OPSICLIPlugin

DEFAULT_EVENTS = [
	"app_state_changed",
	"config_created",
	"config_deleted",
	"config_updated",
	"configState_created",
	"configState_deleted",
	"configState_updated",
	"host_connected",
	"host_created",
	"host_deleted",
	"host_disconnected",
	"host_updated",
	"productOnClient_created",
	"productOnClient_deleted",
	"productOnClient_updated",
	"user_connected",
	"user_disconnected",
]
__version__ = "0.3.0"
__description__ = "This command can be used to interact with the opsi message bus."

logger = get_logger("opsicli")


class EventMessagebusConnection(MessagebusConnection):
	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self.event_types: set[str] = set()
		self.event_data_any: list[dict[str, Any]] = []  # List of data dicts to match against the event data (OR logic)
		self.event_data_all: list[dict[str, Any]] = []  # List of data dicts to match against the event data (AND logic)
		self._waiting_for_event: bool = False
		self._output_type: Literal["message", "event"] | None = None
		self.event_found_event = Event()
		self.result: list[EventMessage] = []

	def _on_event(self, message: EventMessage) -> None:
		if self.event_types and message.event not in self.event_types:
			logger.debug("Received event of unhandled type: %s", message.event)
			return

		if self._output_type:
			data = {"event": message.event} | dict(message.data) if self._output_type == "event" else message.to_dict()
			write_output(data, default_output_format="pretty-json", force_newline=True)

		for event_data in self.event_data_any:
			if all(message.data.get(attr) == val for attr, val in event_data.items()):
				logger.notice("Received event with matching data: %s (data=%s)", message, message.data)
				if self._waiting_for_event:
					self.result = [message]
					self.event_found_event.set()
				return
		for event_data in self.event_data_all:
			if all(message.data.get(attr) == val for attr, val in event_data.items()):
				logger.notice("Received event with matching data: %s (data=%s)", message, message.data)
				if self._waiting_for_event:
					self.result.append(message)
					if len(self.event_data_all) == 1:
						self.event_found_event.set()
					else:
						self.event_data_all.remove(event_data)
				return

		logger.debug("Received event with non matching data: %s (data=%s)", message, message.data)

	def output_events(
		self, types: set[str] | None, output_type: Literal["message", "event"] = "event", timeout: float | None = None
	) -> None:
		self.event_types = types or set()
		self._output_type = output_type
		with self.connection():
			self.subscribe_to_channel([f"event:{evt}" for evt in self.event_types])
			start = time.time()
			while True:
				if timeout and time.time() - start > timeout:
					logger.debug("Timeout reached")
					break
				time.sleep(1)

	def wait_for_event(
		self,
		type: str,
		data_any: list[dict[str, Any]] | None = None,
		data_all: list[dict[str, Any]] | None = None,
		timeout: float | None = None,
	) -> list[EventMessage]:
		self.event_types = {type}
		self.event_data_any = data_any or []
		self.event_data_all = data_all or []
		self._waiting_for_event = True
		logger.notice("Waiting for event of type %r to occur", self.event_types)
		logger.info("Listening until any of %s is found or all of %s is found", self.event_data_any, self.event_data_all)
		try:
			with self.connection():
				self.subscribe_to_channel([f"event:{evt}" for evt in self.event_types])
				self.event_found_event.wait(timeout)
				return self.result
		finally:
			self.result = []
			self.event_found_event.clear()


@click.group(cls=OPSICLIGroup, name="messagebus", short_help="Command group to interact with opsi messagebus")
@click.version_option(__version__, message="opsi-cli plugin messagebus, version %(version)s")
@click.pass_context
@dry_run_handling()
def cli(ctx: click.Context) -> None:
	"""
	This command can be used to interact with opsi messagebus.
	"""
	logger.trace("messagebus command group")


@cli.command(name="get-events", short_help="Get messagebus events")
@click.option("--type", help="Process events of this type only", type=str, multiple=True)
@click.option("--timeout", help="Timeout in seconds", type=float, default=None)
@click.option(
	"--output-type",
	type=click.Choice(["message", "event"], case_sensitive=False),
	help="Output full message or just the event data",
	default="event",
)
def get_events(type: list[str] | None = None, output_type: Literal["message", "event"] = "event", timeout: float | None = None) -> None:
	"""
	Get messagebus events
	"""
	type = type or DEFAULT_EVENTS
	mbus_connection = EventMessagebusConnection()
	try:
		mbus_connection.output_events(types=set(type), output_type=output_type, timeout=timeout)
	except KeyboardInterrupt:
		pass


@cli.command(name="wait-for-event", short_help="Wait for a specific event on the messagebus")
@click.argument("type", type=str)
@click.option("--data", help="Data of the event to wait for", type=str, multiple=True)
@click.option("--timeout", help="Timeout in seconds", type=float, default=None)
def wait_for_event(type: str, data: list[str], timeout: float | None) -> None:
	"""
	Wait for a specific event on the messagebus
	"""
	mbus_connection = EventMessagebusConnection()
	data_list: list[dict[str, Any]] = [{kv[0].strip(): kv[1].strip() for kv in [dat.split("=", 1) for dat in data or []]}]
	result = mbus_connection.wait_for_event(type=type, data_any=data_list, timeout=timeout)
	if not result:
		logger.error("Something went wrong - no matching event received")
		raise RuntimeError("No matching event received")
	write_output(result[0].data, default_output_format="pretty-json")


@cli.command(name="wait-for-host", short_help="Wait for a host to connect to messagebus")
@click.argument("hostname", type=str)
@click.option("--timeout", help="Timeout in seconds", type=float, default=None)
def wait_for_host(hostname: str, timeout: float | None) -> None:
	"""
	Wait for a host to connect to messagebus
	"""
	mbus_connection = EventMessagebusConnection()
	data = {"host": {"type": "OpsiClient", "id": hostname}}
	result = mbus_connection.wait_for_event(type="host_connected", data_any=[data], timeout=timeout)
	if not result:
		logger.error("Something went wrong - no matching event received")
		raise RuntimeError("No matching event received")

	write_output(result[0].data, default_output_format="pretty-json")


@cli.command(name="wait-for-installation", short_help="Wait for a a product installation on a client")
@click.argument("client", type=str)
@click.argument("products", type=str, nargs=-1)
@click.option("--installation-status", help="Status to wait for", type=click.Choice(("installed", "not_installed")), default="installed")
@click.option("--timeout", help="Timeout in seconds", type=float, default=None)
def wait_for_installation(client: str, products: str, installation_status: str, timeout: float | None) -> None:
	"""
	Wait for product installations on a client
	"""
	mbus_connection = EventMessagebusConnection()
	data_any = [
		{"clientId": client, "productId": product, "installationStatus": "unknown", "actionResult": "failed"} for product in products
	]
	data_all = [
		{"clientId": client, "productId": product, "installationStatus": installation_status, "actionResult": "successful"}
		for product in products
	]

	result = mbus_connection.wait_for_event(type="productOnClient_updated", data_any=data_any, data_all=data_all, timeout=timeout)
	if not result:
		logger.error("Something went wrong - no matching event received")
		raise RuntimeError("No matching event received")

	write_output(result[0].data, default_output_format="pretty-json")
	if result[0].data.get("installationStatus") == "unknown":
		logger.error("Installation failed")
		sys.exit(1)


# This class keeps track of the plugins meta-information
class MessagebusPlugin(OPSICLIPlugin):
	name: str = "Messagebus"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
