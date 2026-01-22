# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

jsonrpc plugin
"""

from typing import Any

import orjson
import rich_click as click
from click.shell_completion import CompletionItem
from opsicommon.logging import get_logger

from opsicli.cache import cache
from opsicli.cli_helpers import OPSICLIGroup
from opsicli.config import config
from opsicli.decorators import dry_run_handling
from opsicli.io import deprecation_warning, output_file_is_stdout, read_input, write_output
from opsicli.opsiservice import get_service_connection
from opsicli.plugin import OPSICLIPlugin
from opsicli.types import OutputFormat
from plugins.jsonrpc.data.metadata import command_metadata

__version__ = "0.2.0"

logger = get_logger("opsicli")


def cache_interface(interface: list[dict[str, Any]]) -> None:
	if cache.age("jsonrpc-interface") >= 3600:
		cache.set("jsonrpc-interface", {m["name"]: {"params": m["params"]} for m in interface})
	if cache.age("jsonrpc-interface-raw") >= 3600:
		cache.set("jsonrpc-interface-raw", interface)


@click.group(cls=OPSICLIGroup, name="jsonrpc", short_help="opsi JSONRPC client")
@click.version_option(__version__, message="jsonrpc plugin, version %(version)s")
@click.pass_context
@dry_run_handling()
def cli(ctx: click.Context) -> None:
	"""
	opsi-cli jsonrpc command.
	This command is used to execute JSONRPC requests on an opsi service.
	"""
	logger.trace("jsonrpc command")

	# Cache interface for later
	client = get_service_connection()
	interface = client.jsonrpc("backend_getInterface")
	cache_interface(interface)


@cli.command(short_help="Get JSONRPC method list")
@click.option("--include-deprecated", is_flag=True, default=False, help="Include deprecated methods")
def methods(include_deprecated: bool) -> None:
	"""
	opsi-cli jsonrpc methods subcommand.
	"""
	metadata = command_metadata.get("jsonrpc_methods")
	write_output(
		[m for m in cache.get("jsonrpc-interface-raw") if (not m["deprecated"]) or include_deprecated],
		metadata=metadata,
		default_output_format=OutputFormat.TABLE,
	)


def complete_methods(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[CompletionItem]:
	interface = cache.get("jsonrpc-interface")
	if not interface:
		return []
	items = []
	for method_name in interface:
		if method_name.startswith(incomplete):
			items.append(CompletionItem(method_name))
	return items


def complete_params(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[CompletionItem]:
	interface = cache.get("jsonrpc-interface")
	if not interface:
		return []

	method_info = interface.get(ctx.params["method"])
	if not method_info:
		return []

	params = ctx.params["params"]
	try:
		param_name = method_info["params"][len(params)]
		return [CompletionItem(param_name)]
	except IndexError:
		return []


@cli.command(short_help="Execute JSONRPC")
@click.argument("method", type=str, shell_complete=complete_methods)
@click.argument("params", type=str, nargs=-1, shell_complete=complete_params)
@click.option("--timeout", type=float, help="Timeout in seconds")
def execute(method: str, params: list[str] | None = None, timeout: float | None = None) -> None:
	"""
	opsi-cli jsonrpc execute subcommand.
	"""
	if config.list_attributes:
		raise RuntimeWarning("'--list-attributes' does not support command 'execute'")

	if params:
		logger.debug("Raw parameters: %s", params)
		params = list(params)
		for idx, param in enumerate(params):
			try:
				params[idx] = orjson.loads(param)
			except orjson.JSONDecodeError:
				params[idx] = orjson.loads(f'"{param}"')
	else:
		params = []

	inp_param = read_input()
	if inp_param is not None:
		# TODO: Handle params depending on method parameters
		params.append(inp_param)

	default_output_format = OutputFormat.PRETTY_JSON if output_file_is_stdout() else OutputFormat.JSON

	client = get_service_connection()
	method_interface = client.get_jsonrpc_method(method)
	if method_interface.get("deprecated"):
		deprecation_warning(f"Method {method!r} is deprecated and may not be supported in future versions.")

	logger.info("Calling method %s with params %s", method, params)
	data = client.jsonrpc(method, params, create_objects=False, read_timeout=float(timeout) if timeout else None)
	write_output(data, default_output_format=default_output_format)


class JSONRPCPlugin(OPSICLIPlugin):
	name: str = "JSONRPC"
	description: str = "Opsi JSONRPC API client"
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
