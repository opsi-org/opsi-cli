"""
opsi-cli Basic command line interface for opsi

Test utilities
"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Iterator, Sequence

from click.testing import CliRunner  # type: ignore[import]

from opsicommon.objects import LocalbootProduct, ProductOnDepot, Product
from opsicli.__main__ import main
from opsicli.config import config
from opsicli.opsiservice import ServiceClient

from . import OPSI_HOSTNAME, OPSI_PASSWORD, OPSI_USERNAME

runner = CliRunner(mix_stderr=False)


def run_cli(args: Sequence[str], stdin: list[str] | None = None) -> tuple[int, str, str]:
	result = runner.invoke(main, args, obj={}, catch_exceptions=False, input="\n".join(stdin or []))
	return (result.exit_code, result.stdout, result.stderr)


@contextmanager
def tmp_client(service: ServiceClient, name: str) -> Generator[None, None, None]:
	try:
		service.jsonrpc("host_createOpsiClient", params=[name])
		yield
	finally:
		service.jsonrpc("host_delete", params=[name])


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
def temp_env(**environ: str) -> Iterator[None]:
	old_environ = dict(os.environ)
	os.environ.update(environ)
	try:
		yield
	finally:
		os.environ.clear()
		os.environ.update(old_environ)


@contextmanager
def container_connection() -> Generator[None, None, None]:
	old_username = config.get_values().get("username")
	old_password = config.get_values().get("password")
	old_service = config.get_values().get("service")
	try:
		config.set_values({"username": OPSI_USERNAME})
		config.set_values({"password": OPSI_PASSWORD})
		config.set_values({"service": f"https://{OPSI_HOSTNAME}:4447"})
		config.write_config_files(user_only=True)
		yield
	finally:
		config.set_values({"username": old_username})
		config.set_values({"password": old_password})
		config.set_values({"service": old_service})
		config.write_config_files(user_only=True)
