"""
opsi-cli log plugin
"""

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger

from opsicli.messagebus import FileTransferMessagebusConnection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"
__description__ = "To view and download the logs"


logger = get_logger("opsicli")


@click.group(name="log", short_help="To view and download the logs")
@click.version_option(__version__, message="opsi-cli plugin log, version %(version)s")
def cli() -> None:
	"""
	opsi-cli log command
	This command is used to view and download the logs
	"""
	logger.trace("log command")


@cli.command(short_help="View the logs")
@click.argument("host_id", type=str, nargs=-1, required=True)
async def view(host_id: tuple[str]) -> None:
	"""
	opsi-cli log view subcommand
	"""
	logger.trace("log view subcommand")
	logger.info("Viewing logs for host %s", host_id)
	log_path = f"/var/log/opsi/clientconnect{host_id}.log"
	messagebus_connection = FileTransferMessagebusConnection()
	await messagebus_connection.request_file_download(log_path)


class CustomPlugin(OPSICLIPlugin):
	name: str = "Log"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
