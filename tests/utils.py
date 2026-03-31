# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli Basic command line interface for opsi

Test utilities
"""

import os
import tempfile
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Generator, Sequence

from click.testing import CliRunner
from opsicommon.objects import BoolConfig, ConfigState, LocalbootProduct, OpsiClient, Product, ProductOnDepot, UnicodeConfig

from opsicli.__main__ import main
from opsicli.config import config
from opsicli.opsiservice import ServiceClient

from .conftest import admin_service_connection_params

runner = CliRunner(mix_stderr=False)


def assert_error_contains(stderr: str, expected_parts: tuple[str, ...]) -> None:
	for part in expected_parts:
		assert part in stderr, f"Expected {part!r} in stderr, got: {stderr}"


def run_cli(args: Sequence[str], service_config: bool = True, stdin: list[str] | None = None) -> tuple[int, str, str]:
	context = admin_service_config if service_config else nullcontext
	with context():
		input_str = "\n".join(stdin or [])
		result = runner.invoke(main, args, obj={}, catch_exceptions=False, input=input_str)
		if result.exit_code != 0:
			print("CLI command failed:")
			print(" ".join(args))
			print("input:", input_str)
			print("stdout:", result.stdout)
			print("stderr:", result.stderr)
		return (result.exit_code, result.stdout, result.stderr)


@contextmanager
def tmp_client(service: ServiceClient, name: str, key: str = "") -> Generator[None, None, None]:
	params = [name]
	if key:
		params.append(key)
	try:
		service.jsonrpc("host_createOpsiClient", params=params)
		yield
	finally:
		service.jsonrpc("host_delete", params=[name])


@contextmanager
def tmp_clients(service: ServiceClient, clients: list[OpsiClient]) -> Generator[None, None, None]:
	try:
		service.jsonrpc("host_createObjects", params=[clients])
		yield
	finally:
		service.jsonrpc("host_deleteObjects", params=[clients])


@contextmanager
def tmp_configs(service: ServiceClient, configs: list[BoolConfig | UnicodeConfig]) -> Generator[None, None, None]:
	try:
		service.jsonrpc("config_createObjects", params=[configs])
		yield
	finally:
		service.jsonrpc("config_deleteObjects", params=[configs])


@contextmanager
def tmp_config_states(service: ServiceClient, config_states: list[ConfigState]) -> Generator[None, None, None]:
	try:
		service.jsonrpc("configState_createObjects", params=[config_states])
		yield
	finally:
		service.jsonrpc("configState_deleteObjects", params=[config_states])


@contextmanager
def tmp_product(service: ServiceClient, name: str, product_type: type[Product] = LocalbootProduct) -> Generator[Product, None, None]:
	try:
		depot_id = service.jsonrpc("host_getObjects", [[], {"type": "OpsiConfigserver"}])[0].id
		product = product_type(
			id=name,
			productVersion="1",
			packageVersion="1",
			setupScript="setup.opsiscript",
		)
		product_on_depot = ProductOnDepot(
			productId=product.id,
			productType=product.getType(),
			productVersion=product.productVersion,
			packageVersion=product.packageVersion,
			depotId=depot_id,
		)
		service.jsonrpc("product_createObjects", params=[[product]])
		service.jsonrpc("productOnDepot_createObjects", params=[[product_on_depot]])
		yield product
	finally:
		service.jsonrpc("productOnDepot_delete", params=[name, depot_id])
		service.jsonrpc("product_delete", params=[name])


@contextmanager
def tmp_host_group(
	service: ServiceClient, name: str, clients: set[str] | None = None, parent: str | None = None
) -> Generator[None, None, None]:
	try:
		params = [name]
		if parent:
			params.extend(["", "", parent])
		service.jsonrpc("group_createHostGroup", params=params)
		if clients:
			for client in clients:
				service.jsonrpc("objectToGroup_create", params=["HostGroup", name, client])
		yield
	finally:
		service.jsonrpc("group_deleteObjects", params=[{"id": name}])


@contextmanager
def tmp_product_group(service: ServiceClient, name: str, products: list[str] | None = None) -> Generator[None, None, None]:
	try:
		service.jsonrpc("group_createObjects", params=[{"id": name, "type": "ProductGroup"}])
		for product in products or []:
			service.jsonrpc("objectToGroup_create", params=["ProductGroup", name, product])
		yield
	finally:
		service.jsonrpc("group_deleteObjects", params=[{"id": name}])


@contextmanager
def temp_context() -> Generator[Path, None, None]:
	values = config.get_values()
	try:
		# ignore_cleanup_errors because:
		# Permission Error on windows: file unlink is impossible if handle is opened
		# Problem: add plugin, then load plugin -> open file handle until teardown of python process
		with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tempdir:
			tempdir_path = Path(tempdir)
			config.color = False
			config.python_lib_dir = tempdir_path / "lib"
			config.plugin_user_dir = tempdir_path / "user_plugins"
			config.plugin_system_dir = tempdir_path / "system_plugins"
			yield tempdir_path
	finally:
		config.set_values(values)


@contextmanager
def temp_env(**environ: str | None) -> Generator[dict[str, str], None, None]:
	old_environ = dict(os.environ)
	for name, value in environ.items():
		if value is None:
			os.environ.pop(name, None)
		else:
			os.environ[name] = value
	try:
		yield dict(os.environ.items())
	finally:
		os.environ.clear()
		os.environ.update(old_environ)


@contextmanager
def admin_service_config() -> Generator[tuple[str, str, str], None, None]:
	address, username, password = admin_service_connection_params()
	current_values = config.service, config.username, config.password
	config.service = address
	config.username = username
	config.password = password
	try:
		yield address, username, password
	finally:
		config.service, config.username, config.password = current_values
