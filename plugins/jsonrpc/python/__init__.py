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
from opsicli.io import (
	Attribute,
	Metadata,
	output_file_is_stdout,
	read_input,
	write_output,
	write_output_raw,
)
from opsicli.opsiservice import get_service_connection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"

logger = get_logger("opsicli")


@click.group(name="jsonrpc", short_help="opsi JSONRPC client")
@click.version_option(__version__, message="jsonrpc plugin, version %(version)s")
def cli() -> None:  # pylint: disable=unused-argument
	"""
	opsi-cli jsonrpc command.
	This command is used to execute JSONRPC requests on an opsi service.
	"""
	logger.trace("jsonrpc command")


def cache_interface(interface: list[dict[str, Any]]) -> None:
	if cache.age("jsonrpc-interface") >= 3600:
		cache.set("jsonrpc-interface", {m["name"]: {"params": m["params"]} for m in interface})


@cli.command(short_help="Get JSONRPC method list")
def methods() -> None:
	"""
	opsi-cli jsonrpc methods subcommand.
	"""
	client = get_service_connection()
	if client.interface:
		cache_interface(client.interface)

	metadata = Metadata(
		attributes=[
			Attribute(id="name", description="Method name", identifier=True),
			Attribute(id="params", description="Method params"),
			Attribute(id="deprecated", description="If the method is deprectated"),
			Attribute(id="alternative_method", description="Alternative method, if deprecated"),
			Attribute(id="args", description="Args", selected=False),
			Attribute(id="varargs", description="Varargs", selected=False),
			Attribute(id="keywords", description="Keywords", selected=False),
			Attribute(id="defaults", description="Defaults", selected=False),
		]
	)
	write_output(client.interface, metadata=metadata, default_output_format="table")


def complete_methods(
	ctx: click.Context, param: click.Parameter, incomplete: str  # pylint: disable=unused-argument
) -> list[CompletionItem]:
	interface = cache.get("jsonrpc-interface")
	if not interface:
		return []
	items = []
	for method_name in interface:
		if method_name.startswith(incomplete):
			items.append(CompletionItem(method_name))
	return items


def complete_params(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[CompletionItem]:  # pylint: disable=unused-argument
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
def execute(method: str, params: list[str] | None = None) -> None:  # pylint: disable=too-many-branches
	"""
	opsi-cli jsonrpc execute subcommand.
	"""
	# TODO:
	result_only = True
	if params:
		params = list(params)
		for idx, param in enumerate(params):
			try:
				params[idx] = orjson.loads(param)  # pylint: disable=no-member
			except orjson.JSONDecodeError:  # pylint: disable=no-member
				params[idx] = orjson.loads(f'"{param}"')  # pylint: disable=no-member
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
	if client.interface:
		cache_interface(client.interface)

	client.create_objects = False
	if not result_only and config.output_format == "msgpack":
		client.serialization = "msgpack"
		client.raw_responses = True
	elif not result_only and (config.output_format == "json" or (config.output_format == "auto" and default_output_format == "json")):
		client.serialization = "json"
		client.raw_responses = True
	else:
		client.serialization = "auto"
		client.raw_responses = False

	data = client.execute_rpc(method, params)
	if client.raw_responses:
		write_output_raw(data)
	else:
		write_output(data, default_output_format=default_output_format)


class JSONRPCPlugin(OPSICLIPlugin):
	id: str = "jsonrpc"  # pylint: disable=invalid-name
	name: str = "JSONRPC"
	description: str = "Opsi JSONRPC API client"
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
