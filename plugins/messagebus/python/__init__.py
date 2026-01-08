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
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from threading import Event
from typing import Any, BinaryIO, Generator, Literal

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.messagebus import CONNECTION_USER_CHANNEL
from opsicommon.messagebus.message import (
	Error,
	EventMessage,
	FileChunkMessage,
	FileDownloadInformationMessage,
	FileDownloadRequestMessage,
	FileTransferErrorMessage,
	FileUploadRequestMessage,
	FileUploadResponseMessage,
	FileUploadResultMessage,
	GeneralErrorMessage,
)

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.decorators import dry_run_handling
from opsicli.io import OutputType, console_print, write_output
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
				if not self.event_found_event.wait(timeout):
					raise TimeoutError("Timeout waiting for event")
				return self.result
		finally:
			self.result = []
			self.event_found_event.clear()


class FileDownloadMessagebusConnection(MessagebusConnection):
	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self._error: Error | None = None
		self._file_download_information: FileDownloadInformationMessage | None = None
		self._event_file_download_response_received = Event()
		self._event_file_transfer_completed = Event()
		self._file_handle_ready: Event = Event()
		self._file_handle: BinaryIO | None = None

	def _on_general_error(self, message: GeneralErrorMessage) -> None:
		logger.debug("Received general error: %s", message)
		self._error = message.error
		self._event_file_download_response_received.set()
		self._event_file_transfer_completed.set()

	def _on_file_transfer_error(self, message: FileTransferErrorMessage) -> None:
		logger.debug("Received file transfer error: %s", message)
		self._error = message.error
		self._event_file_download_response_received.set()
		self._event_file_transfer_completed.set()

	def _on_file_download_information(self, message: FileDownloadInformationMessage) -> None:
		logger.debug("Received file download information: %s", message)
		self._file_download_information = message
		self._event_file_download_response_received.set()

	def _on_file_chunk(self, message: FileChunkMessage) -> None:
		logger.debug("Received file chunk: %s", message)
		self._file_handle_ready.wait()
		assert self._file_handle
		self._file_handle.write(message.data)
		if message.last:
			logger.info("Last file chunk received, file transfer completed")
			self._event_file_download_response_received.wait(5)
			self._event_file_transfer_completed.set()

	def download_file(self, client: str, source: PureWindowsPath | PurePosixPath, destination: Path) -> None:
		@contextmanager
		def stdout() -> Generator[BinaryIO, None, None]:
			yield sys.stdout.buffer

		with self.connection():
			file_download_request = FileDownloadRequestMessage(
				sender=CONNECTION_USER_CHANNEL,
				channel=f"host:{client}",
				chunk_size=256_000,
				path=str(source),
			)
			self.send_message(file_download_request)
			try:
				if not self._event_file_download_response_received.wait(timeout=15):
					raise TimeoutError("Timeout waiting for file download response")

				if self._error:
					raise RuntimeError(self._error.message)

				assert self._file_download_information
				logger.notice(
					"Starting download of file '%s' (%d bytes) from client '%s'", source, self._file_download_information.size, client
				)
				ctx = stdout() if destination.name == "-" else open(destination, "wb")
				with ctx as self._file_handle:
					self._file_handle_ready.set()

					self._event_file_transfer_completed.wait()
					if self._error:
						raise RuntimeError(self._error.message)

					logger.notice("File '%s' downloaded successfully to '%s'", source, destination)

			except Exception as exc:
				message = f"Error during file download: {exc}"
				logger.error(message, exc_info=True)
				raise RuntimeError(message) from exc


class FileUploadMessagebusConnection(MessagebusConnection):
	def __init__(self) -> None:
		MessagebusConnection.__init__(self)
		self._error: Error | None = None
		self._file_upload_response: FileUploadResponseMessage | None = None
		self._event_file_upload_response_received = Event()
		self._file_upload_result: FileUploadResultMessage | None = None
		self._event_file_upload_result_received = Event()
		self._file_handle: BinaryIO | None = None

	def _on_general_error(self, message: GeneralErrorMessage) -> None:
		logger.debug("Received general error: %s", message)
		self._error = message.error
		self._event_file_upload_response_received.set()
		self._event_file_upload_result_received.set()

	def _on_file_transfer_error(self, message: FileTransferErrorMessage) -> None:
		logger.debug("Received file transfer error: %s", message)
		self._error = message.error
		self._event_file_upload_response_received.set()
		self._event_file_upload_result_received.set()

	def _on_file_upload_response(self, message: FileUploadResponseMessage) -> None:
		logger.debug("Received file upload response: %s", message)
		self._file_upload_response = message
		self._event_file_upload_response_received.set()

	def _on_file_upload_result(self, message: FileUploadResultMessage) -> None:
		logger.debug("Received file upload result: %s", message)
		self._file_upload_result = message
		self._event_file_upload_result_received.set()

	def upload_file(self, client: str, source: Path, destination: PureWindowsPath | PurePosixPath) -> str:
		@contextmanager
		def stdin() -> Generator[BinaryIO, None, None]:
			yield sys.stdin.buffer

		with self.connection():
			ctx = stdin() if source.name == "-" else open(source, "rb")
			with ctx as self._file_handle:
				size = source.stat().st_size if source.name != "-" else None
				file_upload_request = FileUploadRequestMessage(
					sender=CONNECTION_USER_CHANNEL,
					channel=f"host:{client}",
					content_type="application/octet-stream",
					name=destination.name,
					size=size,
					destination_dir=str(destination.parent),
					# overwrite=True, # TODO: when supported by opsi-client-agent
				)
				self.send_message(file_upload_request)

				try:
					if not self._event_file_upload_response_received.wait(timeout=15):
						raise TimeoutError("Timeout waiting for file upload response")

					if self._error:
						raise RuntimeError(self._error.message)

					assert self._file_upload_response and self._file_handle

					logger.notice("Starting upload of file '%s' (%s bytes) to client '%s'", source, size or "?", client)

					chunk_size = 256_000
					chunk_number = 0
					last = False
					while not last:
						chunk_number += 1
						chunk = self._file_handle.read(chunk_size)
						if len(chunk) < chunk_size:
							last = True
						file_chunk_message = FileChunkMessage(
							sender=CONNECTION_USER_CHANNEL,
							channel=f"host:{client}",
							file_id=self._file_upload_response.file_id,
							data=chunk,
							number=chunk_number,
							last=last,
						)
						self.send_message(file_chunk_message)

					if not self._event_file_upload_result_received.wait(timeout=15):
						raise TimeoutError("Timeout waiting for file upload result")

					if self._error:
						raise RuntimeError(self._error.message)

					assert self._file_upload_result

					logger.notice("File '%s' uploaded successfully to '%s'", source, self._file_upload_result.path)

					return self._file_upload_result.path or str(destination)

				except Exception as exc:
					message = f"Error during file upload: {exc}"
					logger.error(message, exc_info=True)
					raise RuntimeError(message) from exc


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
	try:
		result = mbus_connection.wait_for_event(type=type, data_any=data_list, timeout=timeout)
	except TimeoutError:
		msg = f"Timed out after waiting {timeout:0.1f} seconds for the event"
		logger.error(msg)
		raise RuntimeError(msg) from None

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
	try:
		result = mbus_connection.wait_for_event(type="host_connected", data_any=[data], timeout=timeout)
	except TimeoutError:
		msg = f"Timed out after waiting {timeout:0.1f} seconds for the host to connect"
		logger.error(msg)
		raise RuntimeError(msg) from None

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

	try:
		result = mbus_connection.wait_for_event(type="productOnClient_updated", data_any=data_any, data_all=data_all, timeout=timeout)
	except TimeoutError:
		msg = f"Timed out after waiting {timeout:0.1f} seconds for installation events"
		logger.error(msg)
		raise RuntimeError(msg) from None

	for entry in result:
		write_output(entry.data, default_output_format="pretty-json")
	if result[0].data.get("installationStatus") == "unknown":
		logger.error("Installation failed")
		sys.exit(1)


@cli.command(name="download", short_help="Download file from client via messagebus")
@click.argument("client", type=str)
@click.argument("source", type=str)
@click.argument("destination", default=Path("."), type=click.Path(file_okay=True, dir_okay=True, path_type=Path))
def download_file(client: str, source: str, destination: Path) -> None:
	"""
	Download files from client via messagebus.
	Use '-' as destination to write to stdout.
	"""
	source_path: PureWindowsPath | PurePosixPath
	try:
		source_path = PureWindowsPath(source)
		if not source_path.drive and (r"\\" not in source):
			raise ValueError("Not a Windows path")
	except Exception:
		source_path = PurePosixPath(source)

	if destination.is_dir():
		destination = destination / source_path.name
	mbus_connection = FileDownloadMessagebusConnection()
	mbus_connection.download_file(client=client, source=source_path, destination=destination)
	console_print(f"File '{source_path}' downloaded successfully to '{destination}'.", output_type=OutputType.MESSAGE)


@cli.command(name="upload", short_help="Upload file to client via messagebus")
@click.argument("client", type=str)
@click.argument("source", type=click.Path(file_okay=True, dir_okay=False, path_type=Path))
@click.argument("destination", type=str)
def upload_file(client: str, source: Path, destination: str) -> None:
	"""
	Upload files to client via messagebus.
	Use '-' as source to read from stdin.
	"""
	destination_path: PureWindowsPath | PurePosixPath
	try:
		destination_path = PureWindowsPath(destination)
		if not destination_path.drive and (r"\\" not in destination):
			raise ValueError("Not a Windows path")
	except Exception:
		destination_path = PurePosixPath(destination)

	mbus_connection = FileUploadMessagebusConnection()
	remote_dest = mbus_connection.upload_file(client=client, source=source, destination=destination_path)
	console_print(f"File '{source}' uploaded successfully to '{remote_dest}'.", output_type=OutputType.MESSAGE)


# This class keeps track of the plugins meta-information
class MessagebusPlugin(OPSICLIPlugin):
	name: str = "Messagebus"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
