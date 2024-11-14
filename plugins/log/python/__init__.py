"""
opsi-cli log plugin
"""

import asyncio

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
@click.option("--follow", is_flag=True, help="Follow the log file", default=False)
@click.option(
	"--live",
	is_flag=True,
	help="Show live log file from the client directly (Not implemented); otherwise, show the client logs stored on the server",
	default=False,
)  # TODO: Implement --live option
def view(host_id: str, follow: bool, live: bool) -> None:
	"""
	opsi-cli log view subcommand
	"""
	asyncio.run(view_command(host_id, follow))


async def view_command(host_id: str, follow: bool) -> None:
	logger.trace("log view subcommand")
	logger.info("Viewing logs for host %s", host_id)
	# log_path = f"/var/log/opsi/clientconnect/{host_id}.log"
	log_path = "/var/log/opsi/opsiconfd/test.log"
	messagebus_connection = FileTransferMessagebusConnection(enable_formatting=True)

	try:
		await messagebus_connection.view_file(log_path, follow=follow)
	except KeyboardInterrupt:
		logger.info("Aborting file download for host %s", host_id)
		messagebus_connection.abort_file_download()


class CustomPlugin(OPSICLIPlugin):
	name: str = "Log"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
