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
		self.event_data: list[dict[str, Any]] = []  # List of data dicts to match against the event data (OR logic)
		self._waiting_for_event: bool = False
		self._output_type: Literal["message", "event"] | None = None
		self.event_found_event = Event()
		self.result: EventMessage | None = None

	def _on_event(self, message: EventMessage) -> None:
		if self.event_types and message.event not in self.event_types:
			logger.debug("Received event of unhandled type: %s", message.event)
			return

		data_matches = True
		for event_data in self.event_data:
			data_matches = all(message.data.get(attr) == val for attr, val in event_data.items())
			if data_matches:
				break

		if data_matches:
			# All key-value pairs matched
			logger.notice("Received event with matching data: %s (data=%s)", message, message.data)
			if self._output_type:
				data = {"event": message.event} | dict(message.data) if self._output_type == "event" else message.to_dict()
				write_output(data, default_output_format="pretty-json", force_newline=True)
			if self._waiting_for_event:
				self.result = message
				self.event_found_event.set()
				return
		else:
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

	def wait_for_event(self, type: str, data: list[dict[str, Any]], timeout: float | None = None) -> EventMessage:
		self.event_types = {type}
		self.event_data = data
		self._waiting_for_event = True
		logger.notice("Waiting for event of type %r with data %s to occur", self.event_types, self.event_data)
		try:
			with self.connection():
				self.subscribe_to_channel([f"event:{evt}" for evt in self.event_types])
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
	result = mbus_connection.wait_for_event(type=type, data=data_list, timeout=timeout)
	write_output(result.data, default_output_format="pretty-json")


@cli.command(name="wait-for-host", short_help="Wait for a host to connect to messagebus")
@click.argument("hostname", type=str)
@click.option("--timeout", help="Timeout in seconds", type=float, default=None)
def wait_for_host(hostname: str, timeout: float | None) -> None:
	"""
	Wait for a host to connect to messagebus
	"""
	mbus_connection = EventMessagebusConnection()
	data = {"host": {"type": "OpsiClient", "id": hostname}}
	result = mbus_connection.wait_for_event(type="host_connected", data=[data], timeout=timeout)
	write_output(result.data, default_output_format="pretty-json")


@cli.command(name="wait-for-installation", short_help="Wait for a a product installation on a client")
@click.argument("client", type=str)
@click.argument("product", type=str)
@click.argument("installation-status", type=str)
@click.option("--timeout", help="Timeout in seconds", type=float, default=None)
def wait_for_installation(client: str, product: str, installation_status: str, timeout: float | None) -> None:
	"""
	Wait for a a product installation on a client"
	"""
	mbus_connection = EventMessagebusConnection()
	data = [
		{
			"clientId": client,
			"productId": product,
			"actionRequest": "none",
			"installationStatus": installation_status,
			"actionResult": "successful",
		},
		{"clientId": client, "productId": product, "actionRequest": "none", "installationStatus": "unknown", "actionResult": "failed"},
	]
	result = mbus_connection.wait_for_event(type="productOnClient_updated", data=data, timeout=timeout)
	write_output(result.data, default_output_format="pretty-json")
	if result.data.get("installationStatus") == "unknown":
		logger.error("Installation failed")
		sys.exit(1)


# This class keeps track of the plugins meta-information
class MessagebusPlugin(OPSICLIPlugin):
	name: str = "Messagebus"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
