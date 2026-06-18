# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from datetime import datetime, timezone
from tempfile import NamedTemporaryFile

import rich_click as click
from opsi.logging import get_logger
from opsi.process import run_command

from opsicli.config import config
from opsicli.decorators import dry_run_capable, mutually_exclusive
from opsicli.io import OutputType, console_print, get_editor, get_selected_attributes, read_input, write_output
from opsicli.opsiservice import get_service_connection
from opsicli.types import EditFormat, OutputFormat

from .common import cli, get_msg, process_set, process_where
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
	for client in service_connection.host_getObjects(attributes=attributes, type="OpsiClient", **filter):  # type: ignore[unresolved-attribute]
		client_hash = {attr: val for attr, val in client.to_hash().items() if attr in ("id", "type") or attr in attributes}
		for time_field in ["created", "lastSeen"]:
			if val := client_hash.get(time_field):
				client_hash[time_field] = datetime.fromisoformat(f"{val}Z")
		clients.append(client_hash)
	return clients


def _update_clients(clients: list[dict[str, str | datetime | None]]) -> None:
	if not config.dry_run:
		service_connection = get_service_connection()
		service_connection.host_updateObjects(clients)  # type: ignore[unresolved-attribute]

	console_print(get_msg("clients"), style="green", output_type=OutputType.MESSAGE)
	write_output(data=clients, metadata=CLIENT_METADATA)


@cli.group(name="client", short_help="Manage OPSI clients.")
def client() -> None:
	"""
	View, modify, or add client host-records in the OPSI backend database.
	"""
	pass


@client.command(name="list", short_help="List registered clients.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter criteria matching OPSI host fields (e.g., --where 'hardwareAddress=00:1c:*' or --where 'description=*accounting*').",
)
@click.option(
	"--all",
	is_flag=True,
	help="Show all clients, ignoring any filters.",
)
@mutually_exclusive("all", "where")
@dry_run_capable
def list_clients(where: tuple[str, ...], all: bool) -> None:
	"""
	Query the datastore and display OPSI client host records.

	[bold]Examples:[/]
	  opsi-cli datastore client list --where "id=*.domain.local"
	  opsi-cli datastore client list --where "ipAddress=192.168.1.*"
	  opsi-cli datastore client list --all
	"""
	if not all:
		filter = process_where(where, attributes=CLIENT_METADATA.attributes, operation="list")
	else:
		filter = {}

	selected_attributes = get_selected_attributes(attributes=CLIENT_METADATA.attributes, update_selected=True)
	write_output(
		data=_get_clients_from_service(filter=filter, attributes=selected_attributes),
		metadata=CLIENT_METADATA,
	)


@client.command(name="apply", short_help="Bulk import or modify clients using a JSON/YAML file.")
@dry_run_capable
def apply_clients() -> None:
	"""
	Create new client hosts or update existing client settings in bulk by piping a
	JSON or YAML file containing client definitions via standard input (stdin) or using '--input-file'.
	"""
	clients = _get_clients_from_input()
	if not clients:
		raise ValueError(get_msg("clients", "no_input"))

	get_selected_attributes(attributes=CLIENT_METADATA.attributes, fallback_attributes=list(clients[0]), update_selected=True)
	_update_clients(clients)


@client.command(name="edit", short_help="Open and edit client attributes inside a terminal text editor.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter query to select which client host configurations to pull into the editor (e.g., --where 'id=win10-*').",
)
@dry_run_capable
def edit_clients(where: tuple[str, ...]) -> None:
	"""
	Fetch matching OPSI client definitions and automatically open them in a temporary text
	file using your default system text editor (e.g., nano, vim, notepad). Saving and closing
	the file will instantly write those modifications back to the OPSI database.
	"""
	if not config.interactive:
		raise ValueError("Editing is not possible in non-interactive mode.")

	selected_attributes = get_selected_attributes(attributes=CLIENT_METADATA.attributes, update_selected=True)

	filter = process_where(where, attributes=CLIENT_METADATA.attributes, operation="update")
	clients = _get_clients_from_service(filter=filter, attributes=selected_attributes)
	edit_format = EditFormat.PRETTY_JSON if config.edit_format == EditFormat.AUTO else config.edit_format

	with NamedTemporaryFile(mode="w", encoding="utf-8", suffix=f".{edit_format.file_extension}") as edit_file:
		orig_output_file = config.output_file
		config.input_file = config.output_file = edit_file.name

		write_output(data=clients, metadata=CLIENT_METADATA, default_output_format=OutputFormat(edit_format))

		cmd = get_editor() + [str(edit_file.name)]
		logger.notice("Opening file '%s' with command: %s", edit_file.name, cmd)
		run_command(cmd)

		edited_clients = _get_clients_from_input()
		changed_clients = [client for client in edited_clients if client not in clients]
		logger.notice("Detected %d changed clients.", len(changed_clients))
		if not changed_clients:
			console_print("No changes detected, no clients were updated.", output_type=OutputType.MESSAGE)
			return

		config.output_file = orig_output_file
		_update_clients(changed_clients)


@client.command(name="update", short_help="Directly update specific host fields on targeted clients.")
@click.option(
	"--where",
	type=str,
	multiple=True,
	help="Filter expression to match target client hosts (e.g., --where 'id=pc-*').",
)
@click.option(
	"--set",
	type=str,
	multiple=True,
	help="The host field and the new value to write into it (e.g., --set 'description=Updated Desktop' or --set 'opsiHostKey=1234abcd...').",
)
@dry_run_capable
def update_clients(where: tuple[str, ...], set: tuple[str, ...]) -> None:
	"""
	Modify specific backend host parameters directly on one or more OPSI clients.

	[bold]Examples:[/]
	  opsi-cli datastore client update --where "id=test-client.local" --set "notes=Assigned to Testing Team"
	  opsi-cli datastore client update --where "hardwareAddress=bc:5f:f4:*" --set "description=New Batch Laptops"
	"""
	filter = process_where(where, attributes=CLIENT_METADATA.attributes, operation="update")
	updates: dict[str, str] = process_set(set, attributes=CLIENT_METADATA.attributes)

	selected_attributes = get_selected_attributes(
		attributes=CLIENT_METADATA.attributes,
		fallback_attributes=["id"] + list(updates),
		update_selected=True,
	)

	clients = _get_clients_from_service(filter=filter, attributes=selected_attributes)
	if not clients:
		raise ValueError("No clients found matching the filtering criteria.")

	for client in clients:
		client.update(updates)

	_update_clients(clients)
