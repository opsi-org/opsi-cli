# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import re
from typing import Any, Literal

import rich_click as click
from opsi.logging import get_logger
from opsi.opsi.service.model.object import (
	BoolConfig,
	BoolProductProperty,
	UnicodeConfig,
	UnicodeProductProperty,
)
from opsi.opsi.service.model.type import to_bool_list, to_string_list

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.config import config
from opsicli.io import Attribute, OutputType, console_print, get_separated_entries
from opsicli.opsiservice import ServiceClient
from plugins.datastore.data.help_texts import DATASTORE_HELP as info
from plugins.datastore.data.messages import Error, Help

logger = get_logger("opsicli")

__version__ = "0.1.0"
__description__ = "This command can be used to manage data and objects"


def _parse_value(raw_val: str, operator: str) -> str | list[str]:
	raw_val: str = raw_val.strip()
	has_separator: bool = config.input_separator in raw_val
	separate_input_enabled: bool = not (config.no_input_separation)

	if has_separator:
		console_print(Help.input_separator_detected(), output_type=OutputType.MESSAGE)

	if has_separator and separate_input_enabled:
		if operator != "=":
			raise ValueError(Error.invalid_operator_for_type_list(operator))
		return get_separated_entries(value=raw_val)

	if operator == "=":
		return raw_val

	return operator + raw_val


def _append_value(current: str | list[str], new: str | list[str]) -> list[str]:
	if isinstance(current, str):
		current = [current]
	if isinstance(new, str):
		new = [new]

	return current + new


def _validate_input(
	attribute: Attribute, value: str | list[str], updates: dict[str, str | list[str]], general_help: str
) -> str | list[str]:

	if attribute.validator:
		try:
			value = attribute.validator(value)
		except Exception:  # noqa: BLE001
			raise ValueError(Error.invalid_value_set(attribute.id, str(value), general_help))

	return value


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


def process_where(
	where: tuple[str, ...], *, attributes: list[Attribute], operation: Literal["list", "update", "unlock", "purge", "delete"] = "list"
) -> dict[str, str | list[str]]:
	where = where or ()
	condition_pattern = re.compile(r"^([a-zA-Z_]+)\s*(<|<=|=|>=|>)\s*(.*)$")
	available_attributes_by_id = {attr.id: attr for attr in attributes}
	general_help = Help.general_where(available_attributes=attributes)
	filter: dict[str, str | list[str]] = {}

	for condition in where:
		condition = condition.strip()
		match = condition_pattern.match(condition)
		if not match:
			raise ValueError(Error.invalid_condition_where(condition, general_help))

		attr, operator, value = match.groups()
		attribute = available_attributes_by_id.get(attr)
		value = _parse_value(value, operator)

		if not attribute:
			raise ValueError(Error.invalid_attribute_where(attr, str(value), general_help))

		if attr in filter:
			filter[attr] = _append_value(filter[attr], value)
		else:
			filter[attr] = value

	id_attributes = [attr for attr in attributes if attr.identifier]
	missing_attributes = []
	if operation in ("update", "unlock", "purge", "delete"):
		missing_attributes = [attr.id for attr in id_attributes if attr.id not in filter]

	general_help = Help.general_where(available_attributes=attributes, used_attributes=list(filter), missing_attributes=missing_attributes)
	if operation == "list" and not filter:
		raise ValueError(Error.missing_where(general_help))

	if missing_attributes:
		missing_attr_str = ", ".join(missing_attributes)
		raise ValueError(Error.missing_attribute(operation, missing_attr_str, general_help))

	return filter


def process_set(set: tuple[str, ...], *, attributes: list[Attribute]) -> dict[str, str | list[str]]:
	set = set or ()
	set_pattern: re.Pattern[str] = re.compile(r"^([a-zA -Z]+)\s*=\s*(.*)$")
	attributes_by_id = {attr.id: attr for attr in attributes if not attr.identifier}  # identifying attributes shouldn't be changed
	general_help = Help.general_set(available_attributes=list(attributes_by_id.values()))

	if not set:
		raise ValueError(Error.missing_set(general_help))

	updates: dict[str, str | list[str]] = {}

	for assignment in set:
		assignment = assignment.strip()
		match = set_pattern.match(assignment)
		if not match:
			raise ValueError(Error.invalid_condition_set(assignment, general_help))
		attr, value = map(str.strip, match.groups())
		attribute = attributes_by_id.get(attr)
		value = _parse_value(value, operator="=")

		if not attribute:
			raise ValueError(Error.invalid_attribute_set(attr, str(value), general_help))

		validated_value = _validate_input(attribute, value, updates, general_help)

		if attr in updates:
			updates[attr] = _append_value(updates[attr], validated_value)
		else:
			updates[attr] = validated_value

	return updates


def validate_against_possible_values(
	val: str | list[str], obj: BoolConfig | BoolProductProperty | UnicodeConfig | UnicodeProductProperty
) -> list[str] | list[bool]:
	possible_values: list[str] = obj.possibleValues or []

	if isinstance(obj, BoolConfig | BoolProductProperty):
		if not isinstance(val, str):
			raise ValueError(Error.not_a_single_value(val, obj))  # noqa: TRY004
		if val.lower() not in ["false", "true", "0", "1"]:
			raise ValueError(Error.not_a_possible_value(val, obj))
		return to_bool_list(val)
	else:
		if not isinstance(val, str) and not obj.multiValue:
			raise ValueError(Error.not_a_single_value(val, obj))
		if not obj.editable and val not in possible_values:
			raise ValueError(Error.not_a_possible_value(val, obj))
		return to_string_list(val)


def filter_by_attribute_values(
	data: list[dict[str, Any]], filter: dict[str, str | list[str]], attributes: list[Attribute]
) -> list[dict[str, Any]]:
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
			if isinstance(val, str):
				prepared_filter[attr] = val.capitalize() if val in ("false", "true") else val
			else:
				prepared_filter[attr] = val

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


@click.group(cls=OPSICLIGroup, name="datastore", short_help=info.GENERAL.short)
@click.version_option(__version__, message="datastore plugin, version %(version)s")
@click.pass_context
def cli(ctx: click.Context, **kwargs: str | bool | None) -> None:
	logger.trace("datastore command group")
