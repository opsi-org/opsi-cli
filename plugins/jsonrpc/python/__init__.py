"""
opsi-cli basic command line interface for opsi

jsonrpc plugin
"""

from typing import Any

import orjson
import rich_click as click  # type: ignore[import]
from click.shell_completion import CompletionItem  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli.cache import cache
from opsicli.config import config
from opsicli.io import list_attributes, output_file_is_stdout, read_input, write_output
from opsicli.opsiservice import get_service_connection
from opsicli.plugin import OPSICLIPlugin
from opsicli.utils import get_command_with_subcommand
from plugins.jsonrpc.python.metadata import command_metadata

__version__ = "0.1.0"

logger = get_logger("opsicli")


def cache_interface(interface: list[dict[str, Any]]) -> None:
	if cache.age("jsonrpc-interface") >= 3600:
		cache.set("jsonrpc-interface", {m["name"]: {"params": m["params"]} for m in interface})
	if cache.age("jsonrpc-interface-raw") >= 3600:
		cache.set("jsonrpc-interface-raw", interface)


@click.group(name="jsonrpc", short_help="opsi JSONRPC client")
@click.version_option(__version__, message="jsonrpc plugin, version %(version)s")
@click.pass_context
def cli(ctx: click.Context) -> None:
	"""
	opsi-cli jsonrpc command.
	This command is used to execute JSONRPC requests on an opsi service.
	"""
	logger.trace("jsonrpc command")

	if config.list_attributes:
		command = get_command_with_subcommand(ctx)
		metadata = command_metadata.get(command) if command is not None else None
		if metadata is not None:
			list_attributes(metadata)
			ctx.exit()

	# Cache interface for later
	client = get_service_connection()
	interface = client.jsonrpc("backend_getInterface")
	cache_interface(interface)


@cli.command(short_help="Get JSONRPC method list")
def methods() -> None:
	"""
	opsi-cli jsonrpc methods subcommand.
	"""
	metadata = command_metadata.get("methods")
	write_output(cache.get("jsonrpc-interface-raw"), metadata=metadata, default_output_format="table")


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
def execute(method: str, params: list[str] | None = None) -> None:
	"""
	opsi-cli jsonrpc execute subcommand.
	"""
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
		# TODO: decide by method signature
		# if isinstance(inp_param, list):
		# 	params.extend(inp_param)
		# else:
		params.append(inp_param)

	default_output_format = "pretty-json" if output_file_is_stdout() else "json"

	client = get_service_connection()
	logger.info("Calling method %s with params %s", method, params)
	data = client.jsonrpc(method, params)
	if config.list_attributes and data is not None:
		list_attributes(data, is_data_in_metadata_format=False)
	else:
		write_output(data, default_output_format=default_output_format)


class JSONRPCPlugin(OPSICLIPlugin):
	name: str = "JSONRPC"
	description: str = "Opsi JSONRPC API client"
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
