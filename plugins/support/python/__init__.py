"""
This command can be used to identify potential problems in an opsi environment
"""

from pathlib import Path

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli.io import Attribute, Metadata, write_output
from opsicli.messagebus import JSONRPCMessagebusConnection
from opsicli.opsiservice import get_service_connection
from opsicli.plugin import OPSICLIPlugin

from .worker import category_health_check, default_health_check

__version__ = "0.1.2"
__description__ = "This command can be used to identify potential problems in an opsi environment"


logger = get_logger("opsicli")


@click.group(name="support", short_help="Custom plugin support")
@click.version_option(__version__, message="opsi-cli plugin support, version %(version)s")
def cli() -> None:
	""" """
	logger.trace("support command")


@cli.command(short_help="Print server health check")
@click.argument("category", type=str, required=False)
@click.option("--detailed", help="Enables display of subchecks in full health-health check", is_flag=True, default=False)
def health_check(category: str | None = None, detailed: bool = False) -> None:
	"""
	This command triggers health checks on the server and prints output.
	"""
	metadata = Metadata(
		attributes=[
			Attribute(id="id", description="category of the check - color gives hint of status"),
			Attribute(id="details", description="detailed information of possible problems"),
		],
	)
	if category:
		data = category_health_check(category)
	else:
		data = default_health_check(detailed=detailed)

	write_output(data=data, metadata=metadata)


@cli.command(short_help="Get logfile archive from client")
@click.argument("client", type=str)
@click.option("--path", help="Path to put log archive", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), default=Path())
def client_logs(client: str, path: Path) -> None:
	"""
	This command instructs an opsi client to pack its logs and deliver them as an archive.
	"""
	if path.is_dir():
		path = path / f"{client}.zip"
	messagebus = JSONRPCMessagebusConnection()
	with messagebus.connection():
		result = messagebus.jsonrpc([f"host:{client}"], "getLogs")[f"host:{client}"]
	if not result.get("file_id"):
		raise ValueError(f"Did not get file id for download. Result: {result}")
	service_client = get_service_connection()
	response = service_client.get(f"/file-transfer/{result.get('file_id')}", raw_response=True)
	print(f"Writing log archive at {path}")  # To stdout!
	with open(path, "wb") as file_handle:
		for chunk in response.iter_content(chunk_size=8192):
			file_handle.write(chunk)


class SupportPlugin(OPSICLIPlugin):
	name: str = "Support"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
