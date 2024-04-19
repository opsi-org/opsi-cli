"""
opsi-cli terminal plugin
"""

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli.messagebus import TerminalMessagebusConnection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.3"  # Use this field to track the current version number
__description__ = "This plugin allows to open a remote terminal on a host."

logger = get_logger("opsicli")


@click.command(name="terminal", short_help="Start remote terminal session")
@click.version_option(__version__, message="opsi-cli plugin terminal, version %(version)s")
@click.argument("target", type=str, required=True)
@click.option("--terminal-id", help="Connect to existing terminal session with this id.")
@click.option("--shell", help="Use this shell for the terminal session.")
def cli(target: str, terminal_id: str | None, shell: str | None) -> None:
	"""
	This command starts an interactive console session.
	It connects to the specified target host-id (opsi Client, Depotserver or Configserver).
	"""
	logger.trace("terminal command")
	messagebus = TerminalMessagebusConnection()
	messagebus.run_terminal(target, terminal_id=terminal_id, shell=shell)


class TerminalPlugin(OPSICLIPlugin):
	name: str = "Terminal"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
