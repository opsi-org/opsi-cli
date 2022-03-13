"""
opsi-cli basic command line interface for opsi

jsonrpc plugin
"""

from typing import Any, Dict, List, Optional

import orjson
import rich_click as click  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.config import config
from opsicli.io import output_file_is_stdout, read_input, write_output, write_output_raw
from opsicli.opsiservice import get_service_connection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"


@click.group(name="jsonrpc", short_help="opsi JSONRPC client")
@click.version_option(__version__, message="jsonrpc plugin, version %(version)s")
def cli() -> None:  # pylint: disable=unused-argument
	"""
	opsi-cli jsonrpc command.
	This command is used to execute JSONRPC requests on an opsi service.
	"""
	logger.trace("jsonrpc command")


@cli.command(short_help="Get JSONRPC method list")
def methods() -> None:
	"""
	opsi-cli jsonrpc methods subcommand.
	"""
	client = get_service_connection()
	metadata = {
		"attributes": [
			{"id": "name", "title": "Name", "identifier": True, "selected": True},
			{"id": "params", "title": "Params", "selected": True},
			{"id": "deprecated", "title": "Deprectated", "selected": True},
			{"id": "alternative_method", "title": "Alternative method", "selected": True},
			{"id": "args", "title": "Args", "selected": False},
			{"id": "varargs", "title": "Varargs", "selected": False},
			{"id": "keywords", "title": "Keywords", "selected": False},
			{"id": "defaults", "title": "Defaults", "selected": False},
		]
	}
	write_output(client.interface, metadata=metadata, default_output_format="table")


@cli.command(short_help="Execute JSONRPC")
@click.argument("method", type=str)
@click.argument("params", type=str, nargs=-1)
def execute(method: str, params: Optional[List[str]] = None) -> None:  # pylint: disable=too-many-branches
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
