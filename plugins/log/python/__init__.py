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
@click.argument("host_id", type=str, nargs=1, required=True)
@click.option(
	"--log-type",
	type=click.Choice(["opsiconfd", "opsiclientd"], case_sensitive=False),
	default="opsiclientd",
	help="Specify the type of log to view (opsiconfd or opsiclientd)",
)
@click.option(
	"--live",
	is_flag=True,
	help="Show live log file from the client directly (only available for opsiclientd); otherwise, show the client logs stored on the server",
	default=False,
)
@click.option("--follow", is_flag=True, help="Follow the log file", default=False)
@click.option(
	"--log-level",
	type=click.IntRange(1, 8),
	default=6,
	help="Specify the log level to filter (1 to 8)",
)
@click.option("--color/--no-color", is_flag=True, help="Enable formatting for the log output", default=True)
def view(host_id: str, log_type: str, live: bool, follow: bool, log_level: int, color: bool) -> None:
	"""
	opsi-cli log view subcommand
	"""
	asyncio.run(view_command(host_id, log_type, live, follow, log_level, color))


async def view_command(host_id: str, log_type: str, live: bool, follow: bool, log_level: int, color: bool) -> None:
	logger.trace("log view subcommand")
	logger.info("Viewing logs for host %s", host_id)

	if log_type == "opsiclientd" and not live:
		log_path = f"/var/log/opsi/clientconnect/{host_id}.log"
	elif log_type == "opsiclientd" and live:
		log_path = "/var/log/opsi-client-agent/opsiclientd.log"
	else:
		log_path = "/var/log/opsi/opsiconfd/opsiconfd.log"

	messagebus_connection = FileTransferMessagebusConnection(
		host_id=host_id, log_type=log_type, log_level=log_level, enable_formatting=color, live=live
	)

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
