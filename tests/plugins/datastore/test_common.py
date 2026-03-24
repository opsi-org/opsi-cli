# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from typing import Literal

import pytest

from opsicli.io import Attribute
from plugins.datastore.python.common import process_set, process_where


@pytest.mark.parametrize(
	("where", "attributes", "operation", "expected", "error_match"),
	(
		(
			("id=client1.test.invalid",),
			[Attribute(id="id", identifier=True), Attribute(id="name")],
			"list",
			{"id": "client1.test.invalid"},
			None,
		),
		(
			("id = client1.test.invalid", "name >= test-client"),
			[Attribute(id="id", identifier=True), Attribute(id="name")],
			"update",
			{"id": "client1.test.invalid", "name": "test-client"},
			None,
		),
		(
			tuple(),
			[Attribute(id="id", identifier=True), Attribute(id="name")],
			"list",
			None,
			"At least one filter condition is required",
		),
		(
			("idclient1.test.invalid",),
			[Attribute(id="id", identifier=True)],
			"list",
			None,
			"Invalid filter condition",
		),
		(
			("missing=value",),
			[Attribute(id="id", identifier=True)],
			"list",
			None,
			"Invalid attribute in filter condition",
		),
		(
			("id=client1.test.invalid",),
			[Attribute(id="id", identifier=True), Attribute(id="hostId", identifier=True), Attribute(id="name")],
			"update",
			None,
			"Incomplete filter for update operation",
		),
	),
)
def test_process_where(
	where: tuple[str, ...],
	attributes: list[Attribute],
	operation: Literal["list", "update"],
	expected: dict[str, str] | None,
	error_match: str | None,
) -> None:
	if error_match:
		with pytest.raises(ValueError, match=error_match):
			process_where(where, attributes=attributes, operation=operation)
		return

	assert process_where(where, attributes=attributes, operation=operation) == expected


@pytest.mark.parametrize(
	("set_values", "attributes", "expected", "error_match"),
	(
		(
			("name=test-client",),
			[Attribute(id="name", validator=lambda value: value.strip().upper())],
			{"name": "TEST-CLIENT"},
			None,
		),
		(
			("name=test-client",),
			[Attribute(id="name")],
			{"name": "test-client"},
			None,
		),
		(
			("name=test-client", "description = some text"),
			[
				Attribute(id="name", validator=lambda value: value.strip().upper()),
				Attribute(id="description", validator=lambda value: value.strip()),
			],
			{"name": "TEST-CLIENT", "description": "some text"},
			None,
		),
		(
			tuple(),
			[Attribute(id="name", validator=lambda value: value)],
			None,
			"No attributes specified to update",
		),
		(
			("name:test-client",),
			[Attribute(id="name", validator=lambda value: value)],
			None,
			"Invalid set statement",
		),
		(
			("missing=value",),
			[Attribute(id="name", validator=lambda value: value)],
			None,
			"Invalid attribute in set statement",
		),
		(
			("name=value",),
			[Attribute(id="name", identifier=True, validator=lambda value: value)],
			None,
			"Invalid attribute in set statement",
		),
		(
			("age=not-a-number",),
			[Attribute(id="age", validator=int)],
			None,
			"Invalid value in set statement",
		),
	),
)
def test_process_set(
	set_values: tuple[str, ...],
	attributes: list[Attribute],
	expected: dict[str, str] | None,
	error_match: str | None,
) -> None:
	if error_match:
		with pytest.raises(ValueError, match=error_match):
			process_set(set_values, attributes=attributes)
		return

	assert process_set(set_values, attributes=attributes) == expected
