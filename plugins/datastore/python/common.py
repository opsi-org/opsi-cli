# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import re
from typing import Iterable

import rich_click as click
from opsicommon.logging import get_logger

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.io import Attribute
from opsicli.opsiservice import ServiceClient

logger = get_logger("opsicli")

__version__ = "0.1.0"
__description__ = "This command can be used to manage data and objects"


# handle comma separated object-ids
def get_object_ids(
	service_connection: ServiceClient,
	object_ids: str,
	type: str = "OpsiClient",
) -> list[str]:
	object_id_list = [item.strip() for item in object_ids.split(",")]
	if "all" in object_id_list:
		host_objects = service_connection.host_getObjects(id=[], type=type)  # type: ignore[attr-defined]
		return [obj.id for obj in host_objects]
	return service_connection.host_getIdents(id=object_id_list)  # type: ignore[attr-defined]


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


def process_where(where: tuple[str, ...], *, attributes: list[Attribute]) -> dict[str, str]:
	available_attributes = [a.id for a in attributes]
	condition_pattern = re.compile(r"^([a-zA-Z]+)\s*(<|<=|=|>=|>)\s*(.*)$")
	filter: dict[str, str] = {}
	for condition in where:
		condition = condition.strip()
		if condition == "all":
			return {}
		match = condition_pattern.match(condition)
		if not match:
			raise ValueError(
				f"Invalid filter condition: '{condition}'. Expected format: <attribute><operator><value>. Valid operators are: =, <, <=, >, >=."
			)
		attr, operator, value = match.groups()
		if attr not in available_attributes:
			raise ValueError(
				f"Invalid attribute in filter condition: '{attr}'. Available attributes are: {', '.join(available_attributes)}"
			)
		filter[attr] = value
	return filter


def process_set(set: tuple[str, ...], *, attributes: list[Attribute], exclude_attributes: Iterable[str] | None = None) -> dict[str, str]:
	set_pattern = re.compile(r"^([a-zA-Z]+)\s*=\s*(.*)$")
	attributes_by_id = {attr.id: attr for attr in attributes if not exclude_attributes or attr.id not in exclude_attributes}
	updates: dict[str, str] = {}
	for assignment in set:
		assignment = assignment.strip()
		match = set_pattern.match(assignment)
		if not match:
			raise ValueError(f"Invalid set command: '{assignment}'. Expected format: <attribute>=<value>.")
		attr, value = match.groups()
		attribute = attributes_by_id.get(attr)
		if not attribute:
			raise ValueError(f"Invalid attribute in set command: '{attr}'. Available attributes are: {', '.join(attributes_by_id)}")
		if attribute.validator:
			try:
				updates[attr] = attribute.validator(value)
			except Exception as exc:
				raise ValueError(f"Invalid value for attribute '{attr}': {value}") from exc
	return updates


@click.group(cls=OPSICLIGroup, name="datastore", short_help="Manage objects and data")
@click.version_option(__version__, message="datastore plugin, version %(version)s")
@click.pass_context
def cli(ctx: click.Context, **kwargs: str | bool | None) -> None:
	logger.trace("datastore command group")
