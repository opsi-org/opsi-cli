# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import pytest

from opsicli.io import Attribute
from plugins.datastore.python.common import process_set, process_where


@pytest.mark.parametrize(
	("where", "attributes", "expected", "error_match"),
	(
		(("all",), [Attribute(id="id"), Attribute(id="name")], {}, None),
		(("id=client1.test.invalid",), [Attribute(id="id"), Attribute(id="name")], {"id": "client1.test.invalid"}, None),
		(
			("id = client1.test.invalid", "name >= test-client"),
			[Attribute(id="id"), Attribute(id="name")],
			{"id": "client1.test.invalid", "name": "test-client"},
			None,
		),
		(("idclient1.test.invalid",), [Attribute(id="id")], None, "Invalid filter condition"),
		(("missing=value",), [Attribute(id="id")], None, "Invalid attribute in filter condition"),
	),
)
def test_process_where(
	where: tuple[str, ...], attributes: list[Attribute], expected: dict[str, str] | None, error_match: str | None
) -> None:
	if error_match:
		with pytest.raises(ValueError, match=error_match):
			process_where(where, attributes=attributes)
		return

	assert process_where(where, attributes=attributes) == expected


@pytest.mark.parametrize(
	("set_values", "attributes", "exclude_attributes", "expected", "error_match"),
	(
		(
			("name=test-client",),
			[Attribute(id="name", validator=lambda value: value.strip().upper())],
			None,
			{"name": "TEST-CLIENT"},
			None,
		),
		(
			("name=test-client", "description = some text"),
			[
				Attribute(id="name", validator=lambda value: value.strip().upper()),
				Attribute(id="description", validator=lambda value: value.strip()),
			],
			None,
			{"name": "TEST-CLIENT", "description": "some text"},
			None,
		),
		(
			("name:test-client",),
			[Attribute(id="name", validator=lambda value: value)],
			None,
			None,
			"Invalid set command",
		),
		(
			("missing=value",),
			[Attribute(id="name", validator=lambda value: value)],
			None,
			None,
			"Invalid attribute in set command",
		),
		(
			("name=value",),
			[Attribute(id="name", validator=lambda value: value)],
			("name",),
			None,
			"Invalid attribute in set command",
		),
		(
			("age=not-a-number",),
			[Attribute(id="age", validator=int)],
			None,
			None,
			"Invalid value for attribute 'age': not-a-number",
		),
	),
)
def test_process_set(
	set_values: tuple[str, ...],
	attributes: list[Attribute],
	exclude_attributes: tuple[str, ...] | None,
	expected: dict[str, str] | None,
	error_match: str | None,
) -> None:
	if error_match:
		with pytest.raises(ValueError, match=error_match):
			process_set(set_values, attributes=attributes, exclude_attributes=exclude_attributes)
		return

	assert process_set(set_values, attributes=attributes, exclude_attributes=exclude_attributes) == expected
