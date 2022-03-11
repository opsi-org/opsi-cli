"""
opsi-cli Basic command line interface for opsi

dummy command - proof of concept
"""

from typing import Any, Dict

import requests  # type: ignore[import]
import click
import netifaces  # type: ignore[import] # pylint: disable=import-error

from opsicommon.logging import logger  # type: ignore[import]

from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"


@click.group(name="dummy", short_help="short help for dummy")
@click.version_option(__version__, message="dummy plugin test, version %(version)s")
def cli() -> None:
	"""
	opsi dummy command.
	This is the long help.
	"""
	logger.trace("dummy command")


@cli.command(short_help="short help for subdummy")
def libtest() -> None:
	"""
	opsi dummy subdummy subcommand.
	This is the long help.
	"""
	print(netifaces.gateways())
	print(requests.get("https://opsi.org"))


class DummyPlugin(OPSICLIPlugin):
	id: str = "dummy"  # pylint: disable=invalid-name
	name: str = "Dummy"
	description: str = "A dummy plugin"
	version: str = __version__
	cli = cli