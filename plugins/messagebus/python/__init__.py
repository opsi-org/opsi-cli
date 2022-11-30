"""
opsi-cli messagebus plugin
"""

import asyncio
from typing import Optional

import rich_click as click  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.plugin import OPSICLIPlugin

from .websocket import Messagebus

__version__ = "0.1.0"  # Use this field to track the current version number
__description__ = "This plugin interacts with the opsi message bus."


@click.group(name="messagebus", short_help="Custom plugin messagebus")
@click.version_option(__version__, message="opsi-cli plugin messagebus, version %(version)s")
def cli() -> None:
	"""
	This plugin interacts with the opsi message bus.
	"""
	logger.trace("messagebus command")


@cli.command(short_help="Some example subcommand")
@click.option("--username", default="adminuser", help="username for authentication (websocket)")
@click.option("--password", help="password for authentication (websocket)")
@click.argument("url", nargs=1, default="https://localhost:4447", type=str)
def terminal(username: str, password: Optional[str], url: str) -> None:
	"""
	This subcommand uses the opsi messagebus for an interactive console session.
	"""
	logger.trace("messagebus 'terminal' subcommand")
	messagebus = Messagebus(url, username, password=password)
	asyncio.run(messagebus.run_terminal())


# This class keeps track of the plugins meta-information
class CustomPlugin(OPSICLIPlugin):
	id: str = "messagebus"  # pylint: disable=invalid-name
	name: str = "messagebus"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
