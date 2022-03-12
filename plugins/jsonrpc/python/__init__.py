"""
opsi-cli basic command line interface for opsi

jsonrpc plugin
"""

from typing import List, Optional

import orjson
import rich_click as click  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli import write_output_raw
from opsicli.config import config
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
def execute(method: str, params: Optional[List[str]] = None) -> None:
	"""
	opsi-cli jsonrpc execute subcommand.
	"""
	if params:
		params = []
	else:
		params = [orjson.loads(p) for p in params]  # pylint: disable=no-member

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

	result = client.execute_rpc(method, params)
	if client.raw_responses:
		write_output_raw(result)
	else:
		option = 0
		if config.output_format == "pretty-json":
			option |= orjson.OPT_APPEND_NEWLINE | orjson.OPT_INDENT_2  # pylint: disable=no-member
		write_output_raw(orjson.dumps(result, option=option))  # pylint: disable=no-member


class JSONRPCPlugin(OPSICLIPlugin):
	id: str = "jsonrpc"  # pylint: disable=invalid-name
	name: str = "JSONRPC"
	description: str = "Opsi JSONRPC API client"
	version: str = __version__
	cli = cli
