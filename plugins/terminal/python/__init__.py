# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli terminal plugin
"""

import rich_click as click
from opsicommon.logging import get_logger

from opsicli.cli_helpers import OPSICLICommand
from opsicli.decorators import dry_run_capable
from opsicli.messagebus import TerminalMessagebusConnection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.3"  # Use this field to track the current version number
__description__ = "This plugin allows to open a remote terminal on a host."

logger = get_logger("opsicli")


@click.command(cls=OPSICLICommand, name="terminal", short_help="Start remote terminal session")
@click.version_option(__version__, message="opsi-cli plugin terminal, version %(version)s")
@click.argument("target", type=str, required=True)
@click.option("--terminal-id", help="Connect to existing terminal session with this id.")
@click.option("--shell", help="Use this shell for the terminal session.")
@click.pass_context
@dry_run_capable
def cli(ctx: click.Context, target: str, terminal_id: str | None, shell: str | None) -> None:
	"""
	This command starts an interactive console session.
	It connects to the specified target host-id (opsi Client, Depotserver or Configserver).
	"""
	logger.trace("terminal command")
	messagebus = TerminalMessagebusConnection(terminal_id=terminal_id, shell=shell)
	messagebus.run_terminal(target)


class TerminalPlugin(OPSICLIPlugin):
	name: str = "Terminal"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
