"""
opsi-cli messagebus plugin
"""

from typing import Optional

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli.messagebus import MessagebusConnection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"  # Use this field to track the current version number
__description__ = "This plugin interacts with the opsi message bus."


logger = get_logger("opsicli")


@click.command(name="terminal", short_help="Start remote terminal session")
@click.version_option(__version__, message="opsi-cli plugin messagebus, version %(version)s")
@click.argument("target", type=str, required=True)
@click.option("--terminal-id", help="Connect to existing terminal session with this id.")
def cli(target: str, terminal_id: Optional[str]) -> None:
	"""
	This command starts an interactive console session.
	It connects to the specified target host-id (or the config server if omitted).
	"""
	logger.trace("terminal command")
	messagebus = MessagebusConnection()
	messagebus.run_terminal(target, term_id=terminal_id)


class TerminalPlugin(OPSICLIPlugin):
	id: str = "messagebus"  # pylint: disable=invalid-name
	name: str = "messagebus"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
