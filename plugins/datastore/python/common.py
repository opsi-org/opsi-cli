# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import re
from typing import Any, Literal

import rich_click as click
from opsi.logging import get_logger
from opsi.opsi.service.model.object import BoolConfig, UnicodeConfig
from opsi.opsi.service.model.type import to_bool_list

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.config import config
from opsicli.io import Attribute, get_separated_entries
from opsicli.opsiservice import ServiceClient

logger = get_logger("opsicli")

__version__ = "0.1.0"
__description__ = "This command can be used to manage data and objects"


OPERATION_MATADATA = {
	"delete": {"action": "Deleting", "result": "deleted"},
	"update": {"action": "Updating", "result": "updated"},
	"apply": {"action": "Applying changes to", "result": "changed"},
	"edit": {"action": "Editing", "result": "edited"},
}
MESSAGE_TEMPLATES_ERROR = {
	"no_match": "No {object_name}s found matching the filtering criteria.",
	"no_input": "No input data provided for updating {object_name}s. Please set --input-file.",
}

MESSAGE_TEMPLATE = "{action} {{object_name}}s was successful. Here are the {result} {{object_name}}s."
MESSAGE_TEMPLATE_DRY_RUN = (
	"{action} {{object_name}}s skipped due to dry run.\nHere are the {{object_name}}s that would have been {result}:\n"
)


def get_msg(object_name: str | None = None, event: str | None = None) -> str:
	ctx = click.get_current_context()

	# get last command e.g. (list, apply, edit, ...)
	if event is None:
		event = ctx.command.name
		if event is None:
			raise ValueError("Could not determine event name from Click context.")

	# get second to last command e.g (config-state, client, product, ...)
	if object_name is None:
		parent_ctx = ctx.parent
		if parent_ctx and getattr(parent_ctx, "command", None):
			object_name = parent_ctx.command.name
		else:
			raise ValueError("Could not determine object_name from parent Click context.")

	# early return if error message
	if event in MESSAGE_TEMPLATES_ERROR:
		return MESSAGE_TEMPLATES_ERROR[event].format(object_name=object_name)

	# build the message dynamically
	meta = OPERATION_MATADATA.get(event)
	if not meta:
		raise ValueError(f"No valid event given: {event}")

	if config.dry_run:
		msg = MESSAGE_TEMPLATE_DRY_RUN.format(action=meta["action"], result=meta["result"])
	else:
		msg = MESSAGE_TEMPLATE.format(action=meta["action"], result=meta["result"])

	return msg.format(object_name=object_name)


def create_client_depot_mapping(service_connection: ServiceClient, object_ids: list[str] | None = None) -> dict[str, str]:
	client_to_depot_objects = service_connection.configState_getClientToDepotserver(clientIds=object_ids or [])  # ty: ignore[unresolved-attribute]
	# getClientToDepotserver returns [] for a depot_id
	return {item["clientId"]: item["depotId"] for item in client_to_depot_objects}


def get_depot_to_clients(service_connection: ServiceClient, client_ids: list[str] | None = None) -> dict[str, list[str]]:
	client_to_depot_objects = service_connection.configState_getClientToDepotserver(clientIds=client_ids or [])  # ty: ignore[unresolved-attribute]
	depot_to_clients: dict[str, list[str]] = {}
	for item in client_to_depot_objects:
		depot_id = item["depotId"]
		client_id = item["clientId"]
		if depot_id not in depot_to_clients:
			depot_to_clients[depot_id] = []
		depot_to_clients[depot_id].append(client_id)
	return depot_to_clients


def general_help_for_where(
	available_attributes: list[Attribute], used_attributes: list[str] | None = None, missing_attributes: list[str] | None = None
) -> str:
	used_attributes = used_attributes or []
	missing_attributes = missing_attributes or []

	general_help = (
		'Use one or more `[bold]--where "<attribute><operator><value>"[/]` options to define the filter.\nAvailable attributes are:\n'
	)
	max_attr_len = max(len(attr.id) for attr in available_attributes)
	max_type_len = max(len(str(attr.data_type)) for attr in available_attributes)
	for attr in available_attributes:
		color = "white"
		if attr.id in missing_attributes:
			color = "red"
		elif attr.id in used_attributes:
			color = "green"
		elif attr.identifier:
			color = "cyan"
		type_str = f"({str(attr.data_type)})".ljust(max_type_len + 2)
		general_help += f"  [bold {color}]{attr.id.ljust(max_attr_len)}[/]  {type_str}  {attr.description}\n"
	return general_help


def process_where(
	where: tuple[str, ...], *, attributes: list[Attribute], operation: Literal["list", "update", "unlock", "purge", "delete"] = "list"
) -> dict[str, str]:
	where = where or tuple()
	condition_pattern = re.compile(r"^([a-zA-Z_]+)\s*(<|<=|=|>=|>)\s*(.*)$")
	available_attributes_by_id = {attr.id: attr for attr in attributes}
	general_help = general_help_for_where(available_attributes=attributes)

	filter: dict[str, str] = {}
	for condition in where:
		condition = condition.strip()
		match = condition_pattern.match(condition)
		if not match:
			raise ValueError(
				f"Invalid filter condition: `[bold red]{condition}[/]`.\n"
				f"Expected format: `[bold]<attribute><operator><value>[/]`.\n"
				"Valid operators are: `[bold]=[/]`, `[bold]<[/]`, `[bold]<=[/]`, `[bold]>[/]`, `[bold]>=[/]`.\n\n"
				f"{general_help}"
			)
		attr, operator, value = match.groups()
		attribute = available_attributes_by_id.get(attr)
		# validate the attribute
		if not attribute:
			raise ValueError(f"Invalid attribute in filter condition: `[bold][red]{attr}[/red]={value}[/]`.\n\n{general_help}")

		# combine values if the attribute name is equal // "objectId=jenkins1" "objectId=jenkins2" => {"objectId": "jenkin1, jenkin2"})
		if attr in filter:
			filter[attr] = f"{filter[attr]}, {value}"
		else:
			filter[attr] = value

	id_attributes = [attr for attr in attributes if attr.identifier]
	missing_attributes = []
	if operation in ("update", "unlock", "purge", "delete"):
		missing_attributes = [attr.id for attr in id_attributes if attr.id not in filter]

	general_help = general_help_for_where(
		available_attributes=attributes, used_attributes=list(filter), missing_attributes=missing_attributes
	)
	if operation == "list" and not filter:
		raise ValueError(
			"At least one filter condition is required to prevent unintentional retrieval of large amounts of data.\n"
			"If you intentionally do not want to filter by an attribute, use: `[bold]--all[/]`.\n\n"
			f"{general_help}"
		)
	if missing_attributes:
		raise ValueError(
			f"Incomplete filter for {operation} operation.\n\n"
			f"{general_help}"
			f"\nOn {operation} operations, the filter must contain all identifier attributes.\n"
			f"Missing required attributes: [bold red]{', '.join(missing_attributes)}[/]"
		)
	filter = {k: (v if v != "*" else "") for k, v in filter.items()}  # process wildcards
	return filter


def general_help_for_set(available_attributes: list[Attribute]) -> str:
	general_help = 'Use one or more `[bold]--set "<attribute>=<value>"[/]` options to define the attributes to update.\n\n'
	if not available_attributes:
		return general_help

	general_help += "Available attributes are:\n"
	max_attr_len = max(len(attr.id) for attr in available_attributes)
	max_type_len = max(len(str(attr.data_type)) for attr in available_attributes)
	for attr in available_attributes:
		type_str = f"({str(attr.data_type)})".ljust(max_type_len + 2)
		general_help += f"  [bold white]{attr.id.ljust(max_attr_len)}[/]  {type_str}  {attr.description}\n"
	return general_help


def process_set(set: tuple[str, ...], *, attributes: list[Attribute]) -> dict[str, str]:
	set = set or tuple()
	set_pattern: re.Pattern[str] = re.compile(r"^([a-zA -Z]+)\s*=\s*(.*)$")
	attributes_by_id = {attr.id: attr for attr in attributes if not attr.identifier}  # attributes with identifier shouldn't be changed
	general_help = general_help_for_set(available_attributes=list(attributes_by_id.values()))

	if not set:
		raise ValueError(f"No attributes specified to update.\n\n{general_help}")

	updates: dict[str, str] | dict[str, list[str]] | dict[str, list[bool]] = {}

	for assignment in set:
		assignment = assignment.strip()
		match = set_pattern.match(assignment)
		if not match:
			raise ValueError(
				f"Invalid set statement: `[bold red]{assignment}[/]`.\nExpected format: `[bold]<attribute>=<value>[/]`.\n\n{general_help}"
			)
		attr, value = map(str.strip, match.groups())
		attribute = attributes_by_id.get(attr)
		if not attribute:
			raise ValueError(f"Invalid attribute in set statement: `[bold][red]{attr}[/red]={value}[/]`.\n\n{general_help}")

		if attribute.validator:
			try:
				value = attribute.validator(value)
			except Exception:
				raise ValueError(f"Invalid value in set statement: `[bold]{attr}=[red]{value}[/]`.\n\n{general_help}")

		# Combine values if the attribute name is equal // "objectId=jenkins1" "objectId=jenkins2" => {"objectId": "jenkin1, jenkin2"})
		if updates.get(attr):
			updates[attr] = f"{updates[attr]}, {value}"
		else:
			updates[attr] = value

	return updates


def validate_against_possible_values(val: str, obj: BoolConfig | UnicodeConfig) -> list[str] | list[bool]:
	values = get_separated_entries(val)
	possible_values: list[str] = obj.possibleValues or []
	formatted_possible = ""
	if possible_values:
		formatted_possible = "\n".join([f"- {val}" for val in possible_values])
		formatted_possible = f"[bold]Possible values are:[/]\n[green]{formatted_possible}[/green]"

	if isinstance(obj, BoolConfig):
		if len(values) > 1:
			raise ValueError(f"Only one value is allowed for `[bold][blue]{obj.id}[/][/]`.\n{formatted_possible}")
		if values[0].lower() not in ["false", "true", "0", "1"]:
			raise ValueError(f"Invalid value `{values[0]}` for `[bold][blue]{obj.id}[/][/]`.\n{formatted_possible}")
		return to_bool_list(values)

	elif isinstance(obj, UnicodeConfig):
		if not obj.multiValue and len(values) > 1:
			raise ValueError(f"Multiple values are not allowed for `[bold][blue]{obj.id}[/][/]`.\n{formatted_possible}")
		if not obj.editable and values[0] not in possible_values:
			raise ValueError(f"Invalid value `{values[0]}` for `[bold][blue]{obj.id}[/][/]`.\n{formatted_possible}")
		return values

	return []


def filter_by_attribute_values(data: list[dict[str, Any]], filter: dict[str, str], attributes: list[Attribute]) -> list[dict[str, Any]]:
	"""
	Filters a list of dictionaries based on specific attribute values.

	Args:
	    data: A list of dictionaries representing the records to filter.
	    filter: A mapping of attribute-value pairs.
	    attributes: A list of Attribute objects used to validate filter keys.

	Returns:
	    A list of dictionaries that match all valid criteria in the filter.
	"""
	if not filter:
		return data

	# Map attribute IDs for O(1) lookup during the filtering loop
	available_attributes = {attr.id: attr for attr in attributes}

	# Normalize boolean-like filter strings to capitalized format (e.g., "true" -> "True")
	prepared_filter = {}
	for attr, val in filter.items():
		# Skip filters that do not correspond to known attributes
		if attr in available_attributes:
			prepared_filter[attr] = val.capitalize() if val in ("false", "true") else val

	filtered_data = []

	for entry in data:
		match = True
		for attr, filter_value in prepared_filter.items():
			data_value = entry.get(attr)

			# Normalize data values to string for comparison.
			# Lists are joined by commas to match the filter's string format.
			if isinstance(data_value, list):
				data_value = ", ".join(str(x) for x in data_value)
			else:
				data_value = str(data_value) if data_value is not None else ""

			# compare
			if data_value != filter_value:
				match = False
				break
		if match:
			filtered_data.append(entry)
	return filtered_data


@click.group(cls=OPSICLIGroup, name="datastore", short_help="Manage objects and data")
@click.version_option(__version__, message="datastore plugin, version %(version)s")
@click.pass_context
def cli(ctx: click.Context, **kwargs: str | bool | None) -> None:
	logger.trace("datastore command group")
