# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import subprocess
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile

import rich_click as click
from opsicommon.logging import get_logger

from opsicli.config import config
from opsicli.decorators import dry_run_capable
from opsicli.io import OutputType, console_print, get_editor, get_selected_attributes, read_input, write_output
from opsicli.opsiservice import get_service_connection
from opsicli.types import EditFormat, OutputFormat

from .common import cli, process_set, process_where
from .metadata import CLIENT_METADATA

logger = get_logger("opsicli")


def _get_clients_from_input() -> list[dict[str, str | datetime | None]]:
	data = read_input()
	if not data:
		return []

	clients = []
	for client in data:
		client["type"] = "OpsiClient"
		for time_field in ["created", "lastSeen"]:
			if value := client.get(time_field):
				client[time_field] = datetime.fromisoformat(value).astimezone(timezone.utc).replace(microsecond=0)
		clients.append(client)
	return clients


def _get_clients_from_service(filter: dict[str, str], attributes: list[str]) -> list[dict[str, str | datetime | None]]:
	service_connection = get_service_connection()
	clients = []
	for client in service_connection.host_getObjects(attributes=attributes, type="OpsiClient", **filter):  # type: ignore[attr-defined]
		client_hash = {attr: val for attr, val in client.to_hash().items() if attr in ("id", "type") or attr in attributes}
		for time_field in ["created", "lastSeen"]:
			if val := client_hash.get(time_field):
				client_hash[time_field] = datetime.fromisoformat(f"{val}Z")
		clients.append(client_hash)
	return clients


def _update_clients(clients: list[dict[str, str | datetime | None]]) -> None:
	if config.dry_run:
		msg = "Update skipped due to dry run. Here are the clients that would have been updated:\n"
	else:
		service_connection = get_service_connection()
		service_connection.host_updateObjects(clients)  # type: ignore[attr-defined]
		msg = "Clients updated successfully. Here are the updated clients:\n"

	console_print(msg, style="green", output_type=OutputType.MESSAGE)
	write_output(data=clients, metadata=CLIENT_METADATA)


@cli.group(name="client", short_help="OPSI client related commands.")
def client() -> None:
	"""
	View and change clients
	"""
	pass


@client.command(name="list", short_help="List clients.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter clients.",
)
@dry_run_capable
def list_clients(where: tuple[str, ...]) -> None:
	"""
	View clients.
	"""
	filter = process_where(where, attributes=CLIENT_METADATA.attributes)
	selected_attributes = get_selected_attributes(attributes=CLIENT_METADATA.attributes, update_selected=True)
	write_output(
		data=_get_clients_from_service(filter=filter, attributes=selected_attributes),
		metadata=CLIENT_METADATA,
	)


@client.command(name="apply", short_help="Apply changes to clients.")
@dry_run_capable
def apply_clients() -> None:
	"""
	Apply changes to clients.
	"""
	clients = _get_clients_from_input()
	if not clients:
		raise ValueError("No input data provided for updating clients. Please set --input-file.")

	_update_clients(clients)


@client.command(name="edit", short_help="Edit clients.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter clients.",
)
@dry_run_capable
def edit_clients(where: tuple[str, ...]) -> None:
	"""
	Edit clients.
	"""
	if not config.interactive:
		raise ValueError("Editing is not possible in non-interactive mode.")

	selected_attributes = get_selected_attributes(attributes=CLIENT_METADATA.attributes, update_selected=True)

	filter = process_where(where, attributes=CLIENT_METADATA.attributes)
	clients = _get_clients_from_service(filter=filter, attributes=selected_attributes)
	edit_format = EditFormat.PRETTY_JSON if config.edit_format == EditFormat.AUTO else config.edit_format

	with NamedTemporaryFile(mode="w", encoding="utf-8", suffix=f".{edit_format.file_extension}") as edit_file:
		orig_output_file = config.output_file
		config.input_file = config.output_file = edit_file.name

		write_output(data=clients, metadata=CLIENT_METADATA, default_output_format=OutputFormat(edit_format))

		cmd = get_editor() + [str(edit_file.name)]
		logger.notice("Opening file '%s' with command: %s", edit_file.name, cmd)
		subprocess.run(cmd)

		edited_clients = _get_clients_from_input()
		changed_clients = [client for client in edited_clients if client not in clients]
		logger.notice("Detected %d changed clients.", len(changed_clients))
		if not changed_clients:
			console_print("No changes detected, no clients were updated.", output_type=OutputType.MESSAGE)
			return

		config.output_file = orig_output_file
		_update_clients(changed_clients)


@client.command(name="update", short_help="Update client attributes.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter clients.",
)
@click.option(
	"--set",
	type=str,
	multiple=True,
	help="Set client attributes.",
)
@dry_run_capable
def update_clients(where: tuple[str, ...], set: tuple[str, ...]) -> None:
	"""
	Update attributes of clients.
	"""
	filter = process_where(where, attributes=CLIENT_METADATA.attributes, operation="update")
	updates: dict[str, str] = process_set(set, attributes=CLIENT_METADATA.attributes)

	selected_attributes = get_selected_attributes(
		attributes=CLIENT_METADATA.attributes,
		fallback_attributes=["id"] + list(updates),
		update_selected=True,
	)

	clients = _get_clients_from_service(filter=filter, attributes=selected_attributes)

	for client in clients:
		client.update(updates)

	_update_clients(clients)
