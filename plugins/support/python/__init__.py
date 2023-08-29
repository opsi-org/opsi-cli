"""
This command can be used to identify potential problems in an opsi environment
"""

from pathlib import Path

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli.io import Attribute, Metadata, write_output
from opsicli.messagebus import MessagebusConnection
from opsicli.opsiservice import get_service_connection
from opsicli.plugin import OPSICLIPlugin

from .worker import default_health_check

__version__ = "0.1.1"
__description__ = "This command can be used to identify potential problems in an opsi environment"


logger = get_logger("opsicli")


@click.group(name="support", short_help="Custom plugin support")
@click.version_option(__version__, message="opsi-cli plugin support, version %(version)s")
def cli() -> None:
	""" """
	logger.trace("support command")


@cli.command(short_help="Print server health check")
def health_check() -> None:
	"""
	This command triggers health checks on the server and prints output.
	"""
	metadata = Metadata(
		attributes=[
			Attribute(id="id", description=""),
			Attribute(id="status", description=""),
			Attribute(id="message", description=""),
			Attribute(id="partial_results", description=""),
			Attribute(id="partial_results_status", description=""),
			Attribute(id="partial_results_message", description=""),
		],
	)

	data = default_health_check()

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
	with MessagebusConnection().connection() as messagebus:
		result = messagebus.jsonrpc(f"host:{client}", "getLogs")
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
