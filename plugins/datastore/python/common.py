# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only
import re
from typing import Any, Literal, overload

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.objects import BoolConfig, Config, ProductProperty, UnicodeConfig
from opsicommon.types import forceBoolList

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.io import Attribute, get_separated_entries
from opsicli.opsiservice import ServiceClient

logger = get_logger("opsicli")

__version__ = "0.1.0"
__description__ = "This command can be used to manage data and objects"


# handle comma separated object-ids
def get_object_ids(
	service_connection: ServiceClient,
	object_ids: str | list[str],
	type: str = "OpsiClient",
) -> list[str]:
	if isinstance(object_ids, str):
		object_ids = [item.strip() for item in object_ids.split(",")]

	if "*" in object_ids:
		host_objects = service_connection.host_getObjects(id=[], type=type)  # type: ignore[attr-defined]
		return [obj.id for obj in host_objects]

	return service_connection.host_getIdents(id=object_ids)  # type: ignore[attr-defined]


def create_client_depot_mapping(service_connection: ServiceClient, object_ids: list[str] | None = None) -> dict[str, str]:
	client_to_depot_objects = service_connection.configState_getClientToDepotserver(clientIds=object_ids or [])  # type: ignore[attr-defined]
	# getClientToDepotserver returns [] for a depot_id
	return {item["clientId"]: item["depotId"] for item in client_to_depot_objects}


def get_depot_to_clients(service_connection: ServiceClient, client_ids: list[str] | None = None) -> dict[str, list[str]]:
	client_to_depot_objects = service_connection.configState_getClientToDepotserver(clientIds=client_ids or [])  # type: ignore[attr-defined]
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
		'Use one or more `[bold]--where "<attribute><operator><value>"[/]` options to define the filter.\n'
		'If you intentionally do not want to filter by an attribute, use: `[bold]--where "<attribute>=*"[/]`.\n\n'
		"Available attributes are:\n"
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
	where: tuple[str, ...], *, attributes: list[Attribute], operation: Literal["list", "update"] = "list"
) -> dict[str, str | list[str]]:
	where = where or tuple()
	condition_pattern = re.compile(r"^([a-zA-Z]+)\s*(<|<=|=|>=|>)\s*(.*)$")
	available_attributes_by_id = {attr.id: attr for attr in attributes}
	general_help = general_help_for_where(available_attributes=attributes)

	filter: dict[str, str | list[str]] = {}
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
	if operation == "update":
		missing_attributes = [attr.id for attr in id_attributes if attr.id not in filter]

	if not filter or (operation == "update" and missing_attributes):
		general_help = general_help_for_where(
			available_attributes=attributes, used_attributes=list(filter), missing_attributes=missing_attributes
		)
		if not filter:
			raise ValueError(
				f"At least one filter condition is required to prevent unintentional retrieval of large amounts of data.\n\n{general_help}"
			)
		raise ValueError(
			"Incomplete filter for update operation.\n\n"
			f"{general_help}"
			"\nOn update operations, the filter must contain all identifier attributes.\n"
			f"Missing required attributes: [bold red]{', '.join(missing_attributes)}[/]"
		)
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


@overload
def process_set(set: tuple[str, ...], *, obj: None = None, attributes: list[Attribute]) -> dict[str, str]: ...


@overload
def process_set(
	set: tuple[str, ...], *, obj: Config | ProductProperty, attributes: list[Attribute]
) -> dict[str, list[str] | list[bool]]: ...


def process_set(set: tuple[str, ...], *, attributes: list[Attribute]):
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
				updates[attr] = attribute.validator(value)
			except Exception:
				raise ValueError("Invalid value in set statement: `[bold]{attr}=[red]{value}[/]`.")
		else:
			updates[attr] = value
	return updates


def validate_values_by_obj(val: str, obj: Any) -> list[str] | list[bool]:
	values = get_separated_entries(val)
	possible_values: list[str] = obj.possibleValues if obj else []
	formatted_possible = "\n".join([f"'{val}'" for val in possible_values]) if possible_values else "Any"

	if isinstance(obj, BoolConfig):
		if len(values) > 1:
			raise ValueError(
				f"Only one value is allowed for: `[bold][blue]{obj.id}[/][/]`. \n[bold]Possible values are:[/] \n\n[green]{formatted_possible}[/green]"
			)
		if values[0].lower() not in ["false", "true", "0", "1"]:
			raise ValueError(f"Possible values for: `[bold][blue]{obj.id}[/][/]` \n\n[green]{formatted_possible}[/green]")
		return forceBoolList(values)

	if isinstance(obj, UnicodeConfig):
		if obj.multiValue:
			if not set(values) <= set(possible_values):
				raise ValueError(f"Possible values for: `[bold][blue]{obj.id}[/][/]` \n\n[green]{formatted_possible}[/green]")
		if not obj.multiValue:
			if len(values) > 1:
				raise ValueError(
					f"MultiValues are not allowed for: `[bold][blue]{obj.id}[/][/]` \n[bold]Possible values are[/]: \n\n[green]{formatted_possible}[/green]"
				)
			elif values[0] not in possible_values and possible_values != []:
				raise ValueError(f"Possible values for: `[bold][blue]{obj.id}[/][/]` \n\n[green]{formatted_possible}[/green]")
		return values
	return []


def filter_by_attributes(data: list[dict[str, Any]], filter: dict[str, str | list[str]]) -> list[dict[str, Any]]:
	for attr in filter:
		value = filter[attr]
		data = [item for item in data if item.get(attr) == value]
	return data


@click.group(cls=OPSICLIGroup, name="datastore", short_help="Manage objects and data")
@click.version_option(__version__, message="datastore plugin, version %(version)s")
@click.pass_context
def cli(ctx: click.Context, **kwargs: str | bool | None) -> None:
	logger.trace("datastore command group")
