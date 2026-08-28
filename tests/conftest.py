# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
This file is part of opsi - https://www.opsi.org
"""

from __future__ import annotations

import builtins
import os
import platform
from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
from _pytest.logging import LogCaptureHandler
from _pytest.nodes import Item
from opsi.opsi.service.client import ServiceClient
from opsi.opsi.service.model.object import OpsiConfigserver
from pytest import fixture

from opsicli.cache import cache
from opsicli.config import config
from opsicli.opsiservice import reset_service_connection

PLATFORM = platform.system().lower()

builtins_print = builtins.print


def emit(*args: Any, **kwargs: Any) -> None:
	pass


LogCaptureHandler.emit = emit


@pytest.fixture(autouse=True)
def reset_config() -> None:
	config.reset()


@pytest.fixture(autouse=True)
def clear_cache() -> None:
	cache.clear()


@pytest.fixture(autouse=True)
def reset_print() -> None:
	builtins.print = builtins_print


@pytest.fixture(autouse=True)
def reset_service_client() -> None:
	reset_service_connection()


@pytest.fixture(autouse=True)
def clean_backend() -> None:
	if not _opsi_service_available():
		return
	with get_admin_service_client() as service_client, service_client.connection(connect_messagebus=False):
		delete_host_ids = [
			host.id
			for host in service_client.host_getObjects(attributes=["id", "type"])  # ty: ignore[unresolved-attribute]
			if host.getType() != "OpsiConfigserver"
		]
		if delete_host_ids:
			service_client.host_delete(id=delete_host_ids)  # ty: ignore[unresolved-attribute]
		service_client.product_delete(id=[])  # ty: ignore[unresolved-attribute]


def _update_depot_info() -> None:
	configserver_address = admin_service_connection_params()[0]
	with get_admin_service_client() as service_client:
		server: OpsiConfigserver = service_client.jsonrpc("host_getObjects", [[], {"type": "OpsiConfigserver"}])[0]
		server_host = configserver_address.split("://", 1)[-1].split("/", 1)[0]  # remove protocol
		server.repositoryRemoteUrl = f"webdavs://{server_host}/repository"
		service_client.jsonrpc("host_updateObjects", [server])


def pytest_runtest_setup(item: Item) -> None:
	if _opsi_service_available():
		_update_depot_info()
	for marker in item.iter_markers():
		if marker.name == "opsi_service" and not _opsi_service_available():
			pytest.skip("No opsi service available")
			return
		if marker.name == "not_windows" and PLATFORM == "windows":
			pytest.skip("Not running test on Windows")
			return


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
	# test_decorators.py, test_cli_helpers.py will fail if run after plugins/datastore/test_client.py
	# TODO: Need to investigate and fix the underlying issue, currently we just ensure that these tests are run first
	items.sort(key=lambda item: 1 if item.path.parts[-1] in ("test_decorators.py", "test_cli_helpers.py") else 2)


@lru_cache
def _get_opsi_server_env() -> dict[str, str]:
	env_file = Path("docker/opsi-server/.env")
	env_vars = {}
	for line in env_file.read_text().splitlines():
		line = line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		env_vars[key.strip()] = value.strip().strip('"')
	return env_vars


def admin_service_connection_params() -> tuple[str, str, str]:
	try:
		server_env = _get_opsi_server_env()
		return (
			"https://opsi-server:4447",
			"adminuser",
			server_env["OPSI_ADMIN_PASSWORD"],
		)
	except FileNotFoundError:
		pass
	return (
		os.environ.get("OPSI_HOST") or "",
		os.environ.get("OPSI_USERNAME") or "adminuser",
		os.environ.get("OPSI_ADMIN_PASSWORD") or os.environ.get("OPSI_PASSWORD") or "",
	)


@lru_cache
def _opsi_service_available() -> bool:
	opsi_service_address = admin_service_connection_params()[0]
	if opsi_service_address:
		print("Using opsi service address:", opsi_service_address)
		return True
	print("No opsi service address set.")
	return False


@contextmanager
def get_admin_service_client(user_agent: str | None = None) -> Generator[ServiceClient]:
	address, username, password = admin_service_connection_params()
	service_client = ServiceClient(
		address=address,
		username=username,
		password=password,
		verify="accept_all",
		user_agent=user_agent,
		jsonrpc_create_methods=True,
		jsonrpc_create_objects=True,
	)
	yield service_client
	service_client.stop()


@contextmanager
def get_host_service_client(hostname: str, key: str) -> Generator[ServiceClient]:
	address, _, _ = admin_service_connection_params()
	service_client = ServiceClient(
		address=address,
		username=hostname,
		password=key,
		verify="accept_all",
		jsonrpc_create_methods=True,
		jsonrpc_create_objects=True,
	)
	yield service_client
	service_client.stop()


@fixture()
def admin_service_client() -> Generator[ServiceClient]:
	with get_admin_service_client() as service_client:
		yield service_client
