# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli log plugin
"""

import asyncio

import rich_click as click
from opsicommon.logging import get_logger

from opsicli.decorators import dry_run_handling
from opsicli.messagebus import FileTransferMessagebusConnection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"
__description__ = "A plugin to view logs"


logger = get_logger("opsicli")


@click.group(name="log", short_help="View logs")
@click.version_option(__version__, message="opsi-cli plugin log, version %(version)s")
@click.pass_context
@dry_run_handling()
def cli(ctx: click.Context) -> None:
	"""
	opsi-cli log command.
	This command provides funtionality to view logs using messagebus.
	"""
	logger.trace("log command")


@cli.command(short_help="View logs")
@click.argument("host_id", type=str, required=True)
@click.option(
	"--log-type",
	type=click.Choice(["opsiconfd", "opsiclientd"], case_sensitive=False),
	default="opsiclientd",
	help="Specify the type of log to view.",
	show_default=True,
)
@click.option(
	"--live",
	is_flag=True,
	help="Show live logs directly from the client (only for opsiclientd) or view client logs stored on the server.",
	default=False,
)
@click.option("--follow", is_flag=True, help="Follow the log file for real-time updates.", default=False)
@click.option(
	"--log-level",
	type=click.IntRange(1, 8),
	default=6,
	help="Specify the log level to filter.",
	show_default=True,
)
def view(host_id: str, log_type: str, live: bool, follow: bool, log_level: int) -> None:
	"""
	View logs for a specified host.
	"""
	asyncio.run(view_command(host_id, log_type, live, follow, log_level))


async def view_command(host_id: str, log_type: str, live: bool, follow: bool, log_level: int) -> None:
	logger.trace("log view subcommand")
	logger.info("Viewing logs for host %s", host_id)

	if log_type == "opsiclientd":
		log_path = "{OPSICLIENTD_LOG_FILE_PATH}" if live else f"/var/log/opsi/clientconnect/{host_id}.log"
	else:
		if live:
			logger.error("--live option is only available for log type 'opsiclientd'.")
			raise ValueError("--live option is only available for log type 'opsiclientd'.")
		log_path = "/var/log/opsi/opsiconfd/opsiconfd.log"

	messagebus_connection = FileTransferMessagebusConnection(
		host_id=host_id, log_type=log_type, log_level=log_level, live=live, follow=follow
	)

	try:
		await messagebus_connection.view_file(log_path)
	except KeyboardInterrupt:
		logger.info("Aborting file download for host %s", host_id)
		messagebus_connection.abort_file_download()


class CustomPlugin(OPSICLIPlugin):
	name: str = "Log"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
