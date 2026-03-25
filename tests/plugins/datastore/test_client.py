# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from opsicommon.client.opsiservice import ServiceClient
from opsicommon.objects import OpsiClient

from opsicli.io import read_input_csv
from tests.utils import run_cli, tmp_clients

TEST_CLIENTS = [
	OpsiClient(
		id="pytest-client10.test.tld", description="desc 10", inventoryNumber="inv-0010", created="2021-01-01", lastSeen="2025-09-01"
	),
	OpsiClient(
		id="pytest-client11.test.tld", description="desc 11", inventoryNumber="inv-0011", created="2022-01-01", lastSeen="2025-08-01"
	),
	OpsiClient(
		id="pytest-client20.test.tld", description="desc 20", inventoryNumber="inv-0020", created="2023-01-01", lastSeen="2025-07-01"
	),
	OpsiClient(
		id="pytest-client21.test.tld", description="desc 21", inventoryNumber="inv-0021", created="2024-01-01", lastSeen="2025-06-01"
	),
]


def assert_error_contains(stderr: str, expected_parts: tuple[str, ...]) -> None:
	for part in expected_parts:
		assert part in stderr, f"Expected {part!r} in stderr, got: {stderr}"


@pytest.mark.opsi_service
@pytest.mark.parametrize(
	"command, expected_output, expected_error",
	(
		(
			["--sort-by", "id", "datastore", "client", "list", "--where", "id=*"],
			[
				{
					"description": "desc 10",
					"id": "pytest-client10.test.tld",
					"inventoryNumber": "inv-0010",
					"lastSeen": "2025-09-01T00:00:00+00:00",
				},
				{
					"description": "desc 11",
					"id": "pytest-client11.test.tld",
					"inventoryNumber": "inv-0011",
					"lastSeen": "2025-08-01T00:00:00+00:00",
				},
				{
					"description": "desc 20",
					"id": "pytest-client20.test.tld",
					"inventoryNumber": "inv-0020",
					"lastSeen": "2025-07-01T00:00:00+00:00",
				},
				{
					"description": "desc 21",
					"id": "pytest-client21.test.tld",
					"inventoryNumber": "inv-0021",
					"lastSeen": "2025-06-01T00:00:00+00:00",
				},
			],
			None,
		),
		(
			["--attributes", "lastSeen,id", "--sort-by", "lastSeen", "datastore", "client", "list", "--where", "id=pytest-client1*"],
			[
				{"id": "pytest-client11.test.tld", "lastSeen": "2025-08-01T00:00:00+00:00"},
				{"id": "pytest-client10.test.tld", "lastSeen": "2025-09-01T00:00:00+00:00"},
			],
			None,
		),
		(
			["--attributes", "id", "datastore", "client", "list"],
			None,
			("At least one filter condition is required", "If you intentionally do not want", "Available attributes are:"),
		),
		(
			["--attributes", "id", "datastore", "client", "list", "--where", "unknown=pytest-client1*"],
			None,
			("Invalid attribute in filter condition:", "unknown=pytest-client1*", "Available attributes are:"),
		),
		(
			["--attributes", "id", "datastore", "client", "list", "--where", "invalidfilter"],
			None,
			("Invalid filter condition:", "invalidfilter", "Available attributes are:"),
		),
	),
)
def test_list_clients(
	admin_service_client: ServiceClient,
	command: list[str],
	expected_output: list[dict[str, str]] | None,
	expected_error: tuple[str, ...] | None,
) -> None:
	command = ["--timezone", "UTC", "--output-format", "csv"] + command
	with tmp_clients(admin_service_client, TEST_CLIENTS):
		exit_code, stdout, stderr = run_cli(command)
		if expected_error:
			assert exit_code != 0
			assert_error_contains(stderr, expected_error)
		else:
			assert exit_code == 0
			data = read_input_csv(stdout.encode("utf-8"))
			assert data == expected_output


@pytest.mark.opsi_service
@pytest.mark.parametrize(
	"command, expected_output, expected_values, expected_error",
	(
		(
			[
				"--sort-by",
				"id",
				"datastore",
				"client",
				"update",
				"--where",
				"id=*",
				"--set",
				"description=updated",
				"--set",
				"inventoryNumber=updated",
			],
			[
				{
					"description": "updated",
					"id": "pytest-client10.test.tld",
					"inventoryNumber": "updated",
				},
				{
					"description": "updated",
					"id": "pytest-client11.test.tld",
					"inventoryNumber": "updated",
				},
				{
					"description": "updated",
					"id": "pytest-client20.test.tld",
					"inventoryNumber": "updated",
				},
				{
					"description": "updated",
					"id": "pytest-client21.test.tld",
					"inventoryNumber": "updated",
				},
			],
			[
				{
					"description": "updated",
					"id": "pytest-client10.test.tld",
					"inventoryNumber": "updated",
					"lastSeen": "2025-09-01 00:00:00",
				},
				{
					"description": "updated",
					"id": "pytest-client11.test.tld",
					"inventoryNumber": "updated",
					"lastSeen": "2025-08-01 00:00:00",
				},
				{
					"description": "updated",
					"id": "pytest-client20.test.tld",
					"inventoryNumber": "updated",
					"lastSeen": "2025-07-01 00:00:00",
				},
				{
					"description": "updated",
					"id": "pytest-client21.test.tld",
					"inventoryNumber": "updated",
					"lastSeen": "2025-06-01 00:00:00",
				},
			],
			None,
		),
		(
			[
				"--attributes",
				"inventoryNumber,description",
				"datastore",
				"client",
				"update",
				"--where",
				"id=pytest-client11.test.tld",
				"--where",
				"inventoryNumber=inv-001*",
				"--where",
				"description=desc 11",
				"--set",
				"description=updated",
			],
			[
				{
					"inventoryNumber": "inv-0011",
					"description": "updated",
				}
			],
			[
				{
					"description": "desc 10",
					"id": "pytest-client10.test.tld",
					"inventoryNumber": "inv-0010",
					"lastSeen": "2025-09-01 00:00:00",
				},
				{
					"description": "updated",
					"id": "pytest-client11.test.tld",
					"inventoryNumber": "inv-0011",
					"lastSeen": "2025-08-01 00:00:00",
				},
				{
					"description": "desc 20",
					"id": "pytest-client20.test.tld",
					"inventoryNumber": "inv-0020",
					"lastSeen": "2025-07-01 00:00:00",
				},
				{
					"description": "desc 21",
					"id": "pytest-client21.test.tld",
					"inventoryNumber": "inv-0021",
					"lastSeen": "2025-06-01 00:00:00",
				},
			],
			None,
		),
		(
			[
				"--dry-run",
				"--attributes",
				"inventoryNumber,description",
				"datastore",
				"client",
				"update",
				"--where",
				"id=pytest-client11.test.tld",
				"--where",
				"inventoryNumber=inv-001*",
				"--where",
				"description=desc 11",
				"--set",
				"description=updated",
			],
			[
				{
					"inventoryNumber": "inv-0011",
					"description": "updated",
				}
			],
			[
				{
					"description": "desc 10",
					"id": "pytest-client10.test.tld",
					"inventoryNumber": "inv-0010",
					"lastSeen": "2025-09-01 00:00:00",
				},
				{
					"description": "desc 11",
					"id": "pytest-client11.test.tld",
					"inventoryNumber": "inv-0011",
					"lastSeen": "2025-08-01 00:00:00",
				},
				{
					"description": "desc 20",
					"id": "pytest-client20.test.tld",
					"inventoryNumber": "inv-0020",
					"lastSeen": "2025-07-01 00:00:00",
				},
				{
					"description": "desc 21",
					"id": "pytest-client21.test.tld",
					"inventoryNumber": "inv-0021",
					"lastSeen": "2025-06-01 00:00:00",
				},
			],
			None,
		),
		(
			[
				"--dry-run",
				"--attributes",
				"inventoryNumber,description",
				"datastore",
				"client",
				"update",
				"--where",
				"inventoryNumber=inv-001*",
				"--where",
				"description=desc 11",
				"--set",
				"description=updated",
			],
			None,
			[
				{
					"description": "desc 10",
					"id": "pytest-client10.test.tld",
					"inventoryNumber": "inv-0010",
					"lastSeen": "2025-09-01 00:00:00",
				},
				{
					"description": "desc 11",
					"id": "pytest-client11.test.tld",
					"inventoryNumber": "inv-0011",
					"lastSeen": "2025-08-01 00:00:00",
				},
				{
					"description": "desc 20",
					"id": "pytest-client20.test.tld",
					"inventoryNumber": "inv-0020",
					"lastSeen": "2025-07-01 00:00:00",
				},
				{
					"description": "desc 21",
					"id": "pytest-client21.test.tld",
					"inventoryNumber": "inv-0021",
					"lastSeen": "2025-06-01 00:00:00",
				},
			],
			("Incomplete filter for update operation.", "Missing required attributes: id"),
		),
		(
			[
				"datastore",
				"client",
				"update",
				"--where",
				"id=*",
				"--set",
				"invalid=updated",
			],
			None,
			[
				{
					"description": "desc 10",
					"id": "pytest-client10.test.tld",
					"inventoryNumber": "inv-0010",
					"lastSeen": "2025-09-01 00:00:00",
				},
				{
					"description": "desc 11",
					"id": "pytest-client11.test.tld",
					"inventoryNumber": "inv-0011",
					"lastSeen": "2025-08-01 00:00:00",
				},
				{
					"description": "desc 20",
					"id": "pytest-client20.test.tld",
					"inventoryNumber": "inv-0020",
					"lastSeen": "2025-07-01 00:00:00",
				},
				{
					"description": "desc 21",
					"id": "pytest-client21.test.tld",
					"inventoryNumber": "inv-0021",
					"lastSeen": "2025-06-01 00:00:00",
				},
			],
			("Invalid attribute in set statement:", "invalid=updated", "Available attributes are:"),
		),
		(
			[
				"datastore",
				"client",
				"update",
				"--where",
				"id=*",
				"--set",
				"opsiHostKey=invalid-value",
			],
			None,
			[
				{
					"description": "desc 10",
					"id": "pytest-client10.test.tld",
					"inventoryNumber": "inv-0010",
					"lastSeen": "2025-09-01 00:00:00",
				},
				{
					"description": "desc 11",
					"id": "pytest-client11.test.tld",
					"inventoryNumber": "inv-0011",
					"lastSeen": "2025-08-01 00:00:00",
				},
				{
					"description": "desc 20",
					"id": "pytest-client20.test.tld",
					"inventoryNumber": "inv-0020",
					"lastSeen": "2025-07-01 00:00:00",
				},
				{
					"description": "desc 21",
					"id": "pytest-client21.test.tld",
					"inventoryNumber": "inv-0021",
					"lastSeen": "2025-06-01 00:00:00",
				},
			],
			("Invalid value in set statement:", "opsiHostKey=invalid-value", "Available attributes are:"),
		),
	),
)
def test_update_clients(
	admin_service_client: ServiceClient,
	command: list[str],
	expected_output: list[dict[str, str]] | None,
	expected_values: list[dict[str, str | None]],
	expected_error: tuple[str, ...] | None,
) -> None:
	command = ["--timezone", "UTC", "--output-format", "csv"] + command
	with tmp_clients(admin_service_client, TEST_CLIENTS):
		exit_code, stdout, stderr = run_cli(command)
		if expected_error:
			assert exit_code != 0
			assert_error_contains(stderr, expected_error)
		else:
			assert exit_code == 0
			data = read_input_csv(stdout.encode("utf-8"))
			assert data == expected_output

		hosts = admin_service_client.host_getObjects(id=[c.id for c in TEST_CLIENTS], type="OpsiClient")  # type: ignore[attr-defined]
		for host, expected_host in zip(sorted(hosts, key=lambda h: h.id), expected_values, strict=True):
			for key, expected_val in expected_host.items():
				actual_val = getattr(host, key)
				if isinstance(expected_val, str) and expected_val.endswith("Z"):
					expected_val = expected_val[:-1] + "+00:00"
				assert actual_val == expected_val, f"Mismatch for host {host.id} attribute {key}: expected {expected_val}, got {actual_val}"


@pytest.mark.opsi_service
def test_edit_clients_non_interactive(admin_service_client: ServiceClient) -> None:
	with tmp_clients(admin_service_client, TEST_CLIENTS):
		exit_code, _stdout, _stderr = run_cli(["--non-interactive", "datastore", "client", "edit", "--where", "id=*"])
		assert exit_code != 0
		assert "Editing is not possible in non-interactive mode." in _stderr


@pytest.mark.opsi_service
@pytest.mark.parametrize("dry_run", [True, False])
def test_edit_clients(admin_service_client: ServiceClient, dry_run: bool) -> None:
	with tmp_clients(admin_service_client, TEST_CLIENTS):

		def fake_editor(cmd: list[str]) -> None:
			edit_file = Path(cmd[-1])
			clients = json.loads(edit_file.read_text(encoding="utf-8"))
			for client in clients:
				if client["id"].startswith("pytest-client1"):
					client["description"] = "updated description"
					client["inventoryNumber"] = "updated inventory number"
			edit_file.write_text(json.dumps(clients, indent=2), encoding="utf-8")

		with patch("subprocess.run", side_effect=fake_editor):
			exit_code, _stdout, _stderr = run_cli(
				(["--dry-run"] if dry_run else []) + ["--interactive", "datastore", "client", "edit", "--where", "id=*"]
			)

		assert exit_code == 0
		hosts = admin_service_client.host_getObjects(id=[c.id for c in TEST_CLIENTS], type="OpsiClient")  # type: ignore[attr-defined]
		for host in hosts:
			if host.id.startswith("pytest-client1") and not dry_run:
				assert host.description == "updated description"
				assert host.inventoryNumber == "updated inventory number"
			else:
				assert host.description.startswith("desc")
				assert host.inventoryNumber.startswith("inv-00")


@pytest.mark.opsi_service
@pytest.mark.parametrize("dry_run", [True, False])
def test_apply_clients(admin_service_client: ServiceClient, dry_run: bool) -> None:
	with tmp_clients(admin_service_client, TEST_CLIENTS):
		apply_data = [
			{
				"id": "pytest-client10.test.tld",
				"inventoryNumber": "applied-0010",
				"lastSeen": "2025-09-10T00:00:00+00:00",
			},
			{
				"id": "pytest-client21.test.tld",
				"inventoryNumber": "applied-0021",
				"lastSeen": "2025-06-10T00:00:00+00:00",
			},
		]

		exit_code, stdout, _stderr = run_cli(
			(["--dry-run"] if dry_run else []) + ["--timezone", "UTC", "--output-format", "csv", "datastore", "client", "apply"],
			stdin=[json.dumps(apply_data)],
		)

		assert exit_code == 0
		assert read_input_csv(stdout.encode("utf-8")) == [
			{
				"id": "pytest-client10.test.tld",
				"inventoryNumber": "applied-0010",
				"lastSeen": "2025-09-10T00:00:00+00:00",
			},
			{
				"id": "pytest-client21.test.tld",
				"inventoryNumber": "applied-0021",
				"lastSeen": "2025-06-10T00:00:00+00:00",
			},
		]

		hosts = admin_service_client.host_getObjects(id=[c.id for c in TEST_CLIENTS], type="OpsiClient")  # type: ignore[attr-defined]
		hosts_by_id = {host.id: host for host in hosts}

		if dry_run:
			assert hosts_by_id["pytest-client10.test.tld"].inventoryNumber == "inv-0010"
			assert hosts_by_id["pytest-client10.test.tld"].lastSeen == "2025-09-01 00:00:00"
			assert hosts_by_id["pytest-client21.test.tld"].inventoryNumber == "inv-0021"
			assert hosts_by_id["pytest-client21.test.tld"].lastSeen == "2025-06-01 00:00:00"
		else:
			assert hosts_by_id["pytest-client10.test.tld"].inventoryNumber == "applied-0010"
			assert hosts_by_id["pytest-client10.test.tld"].lastSeen == "2025-09-10 00:00:00"
			assert hosts_by_id["pytest-client21.test.tld"].inventoryNumber == "applied-0021"
			assert hosts_by_id["pytest-client21.test.tld"].lastSeen == "2025-06-10 00:00:00"

		assert hosts_by_id["pytest-client11.test.tld"].inventoryNumber == "inv-0011"
		assert hosts_by_id["pytest-client11.test.tld"].lastSeen == "2025-08-01 00:00:00"
		assert hosts_by_id["pytest-client20.test.tld"].inventoryNumber == "inv-0020"
		assert hosts_by_id["pytest-client20.test.tld"].lastSeen == "2025-07-01 00:00:00"
