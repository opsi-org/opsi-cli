"""
opsi-cli basic command line interface for opsi

jsonrpc plugin
"""

from typing import Any, Dict, List, Optional

import orjson
import rich_click as click  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli import write_output, write_output_raw
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
	elif config.output_format == "pretty-json":
		write_output_raw(orjson.dumps(data, option=orjson.OPT_APPEND_NEWLINE | orjson.OPT_INDENT_2))  # pylint: disable=no-member
	else:
		stt = get_structure_type(data)
		if stt == List:
			metadata = {"columns": [{"id": "value0"}]}
		elif stt == List[List]:
			metadata = {"columns": [{"id": f"value{idx}"} for idx in range(len(data[0]))]}
		elif stt == List[Dict]:
			metadata = {"columns": [{"id": key} for key in get_attributes(data)]}
		else:
			raise RuntimeError(f"Output-format {config.output_format!r} does not support stucture {stt!r}")
		write_output(metadata, data)


def get_attributes(data, all_elements=True) -> List[str]:
	attributes_set = set()
	for element in data:
		attributes_set |= set(element.keys())
		if not all_elements:
			break
	attributes = sorted(list(attributes_set))
	if len(attributes) > 1:
		idx = attributes.index("id")
		if idx > 0:
			attributes.insert(0, attributes.pop(idx))
	return attributes


def get_structure_type(data):
	if isinstance(data, list):
		if isinstance(data[0], list):
			return List[List]
		if isinstance(data[0], dict):
			return List[Dict]
		return List
	if isinstance(data, dict):
		return Dict
	return None


class JSONRPCPlugin(OPSICLIPlugin):
	id: str = "jsonrpc"  # pylint: disable=invalid-name
	name: str = "JSONRPC"
	description: str = "Opsi JSONRPC API client"
	version: str = __version__
	cli = cli
