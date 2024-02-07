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

from opsicli.__main__ import main
from opsicli.config import config
from opsicli.opsiservice import ServiceClient

from . import OPSI_HOSTNAME

runner = CliRunner()


def run_cli(args: Sequence[str], stdin: list[str] | None = None) -> tuple[int, str]:
	result = runner.invoke(main, args, obj={}, catch_exceptions=False, input="\n".join(stdin or []))
	return (result.exit_code, result.output)


@contextmanager
def tmp_client(service: ServiceClient, name: str) -> Generator[None, None, None]:
	try:
		service.jsonrpc("host_createOpsiClient", params=[name])
		yield
	finally:
		service.jsonrpc("host_delete", params=[name])


@contextmanager
def tmp_product(service: ServiceClient, name: str) -> Generator[None, None, None]:
	try:
		product_dict = {
			"id": name,
			"type": "LocalbootProduct",
			"productVersion": "1",
			"packageVersion": "1",
			"setupScript": "setup.opsiscript",
		}
		depot_id = service.jsonrpc("host_getObjects", [[], {"type": "OpsiConfigserver"}])[0]["id"]
		service.jsonrpc("product_createObjects", params=[product_dict])
		pod_dict = {"productId": name, "depotId": depot_id, "productType": "LocalbootProduct", "productVersion": "1", "packageVersion": "1"}
		service.jsonrpc("productOnDepot_createObjects", params=[pod_dict])
		yield
	finally:
		service.jsonrpc("productOnDepot_delete", params=[name, depot_id])
		service.jsonrpc("product_delete", params=[name])


@contextmanager
def tmp_host_group(
	service: ServiceClient, name: str, clients: list[str] | None = None, parent: str | None = None
) -> Generator[None, None, None]:
	try:
		params = [name]
		if parent:
			params.extend(["", "", parent])
		service.jsonrpc("group_createHostGroup", params=params)
		for client in clients or []:
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
		config.set_values({"username": "adminuser"})
		config.set_values({"password": "vhahd8usaz"})
		config.set_values({"service": f"https://{OPSI_HOSTNAME}:4447"})
		yield
	finally:
		config.set_values({"username": old_username})
		config.set_values({"password": old_password})
		config.set_values({"service": old_service})
