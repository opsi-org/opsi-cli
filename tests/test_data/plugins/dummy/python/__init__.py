"""
opsi-cli Basic command line interface for opsi

dummy command - proof of concept
"""

import click
import git  # type: ignore[import] # pylint: disable=import-error  # noqa: F401
import netifaces  # type: ignore[import] # pylint: disable=import-error
import requests  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"

logger = get_logger("opsicli")


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
	print(requests.get("https://gitlab.uib.gmbh", timeout=10))


class DummyPlugin(OPSICLIPlugin):
	id: str = "dummy"
	name: str = "Dummy"
	description: str = "A dummy plugin"
	version: str = __version__
	cli = cli
