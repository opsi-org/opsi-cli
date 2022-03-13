"""
opsi-cli basic command line interface for opsi

jsonrpc plugin
"""

from typing import Any, Dict, List, Optional

import orjson
import rich_click as click  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.config import config
from opsicli.io import read_input_raw, write_output, write_output_raw
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


@cli.command(short_help="Execute JSONRPC")
@click.argument("method", type=str)
@click.argument("params", type=str, nargs=-1)
def execute(method: str, params: Optional[List[str]] = None) -> None:  # pylint: disable=too-many-branches
	"""
	opsi-cli jsonrpc execute subcommand.
	"""
	if params:
		params = list(params)
		for idx, param in enumerate(params):
			try:
				params[idx] = orjson.loads(param)  # pylint: disable=no-member
			except orjson.JSONDecodeError:  # pylint: disable=no-member
				params[idx] = orjson.loads(f'"{param}"')  # pylint: disable=no-member
	else:
		params = []

	input_str = read_input_raw()
	if input_str:
		inp_param = orjson.loads(input_str)  # pylint: disable=no-member
		if isinstance(inp_param, list):
			params.extend(inp_param)
		else:
			params.append(inp_param)

	client = get_service_connection()
	client.create_objects = False
	if config.output_format == "msgpack":
		client.serialization = "msgpack"
		client.raw_responses = True
	elif config.output_format in ("auto", "json"):
		client.serialization = "json"
		client.raw_responses = True
	else:
		client.serialization = "auto"
		client.raw_responses = False

	data = client.execute_rpc(method, params)
	if client.raw_responses:
		write_output_raw(data)
	else:
		write_output(data)


class JSONRPCPlugin(OPSICLIPlugin):
	id: str = "jsonrpc"  # pylint: disable=invalid-name
	name: str = "JSONRPC"
	description: str = "Opsi JSONRPC API client"
	version: str = __version__
	cli = cli
