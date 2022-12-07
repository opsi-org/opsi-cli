"""
opsi-cli messagebus plugin
"""

from typing import Optional

import rich_click as click  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.plugin import OPSICLIPlugin

from .websocket import MessagebusConnection

__version__ = "0.1.0"  # Use this field to track the current version number
__description__ = "This plugin interacts with the opsi message bus."


@click.group(name="messagebus", short_help="Custom plugin messagebus")
@click.pass_context
@click.version_option(__version__, message="opsi-cli plugin messagebus, version %(version)s")
def cli(ctx: click.Context) -> None:
	"""
	This plugin interacts with the opsi message bus.
	"""
	logger.trace("messagebus command")
	ctx.obj = MessagebusConnection()


@cli.command(short_help="Start terminal session via messagebus")
@click.pass_context
@click.option("--terminal-id", help="Connect to existing terminal session with this id.")
@click.argument("target", type=str, required=False)
def terminal(ctx: click.Context, terminal_id: Optional[str], target: Optional[str]) -> None:
	"""
	This subcommand uses the opsi messagebus for an interactive console session.
	It connects to the specified target host-id (or if omitted the config server)
	"""
	logger.trace("messagebus 'terminal' subcommand")
	ctx.obj.run_terminal(term_id=terminal_id, target=target)


# This class keeps track of the plugins meta-information
class MessagebusPlugin(OPSICLIPlugin):
	id: str = "messagebus"  # pylint: disable=invalid-name
	name: str = "messagebus"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
