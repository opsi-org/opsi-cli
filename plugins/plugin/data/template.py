"""
template for opsi-cli plugins
"""

import click
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.plugin import OPSICLIPlugin

__version__ = "##VERSION##"  # Use this field to track the current version number
__description__ = "##DESCRIPTION##"


@click.group(name="##ID##", short_help="Custom plugin ##NAME##")
@click.version_option(__version__, message="opsi-cli plugin ##NAME##, version %(version)s")
def cli() -> None:  # The docstring is used in opsi-cli ##ID## --help
	"""
	##DESCRIPTION##
	"""
	logger.trace("##ID## command")


@cli.command(short_help="Some example subcommand")
@click.argument("--exampleargument", "-a", help="example for an argument", default="defaultvalue")
@click.option("--exampleoption", help="example for an option option", is_flag=True)
def subcommand(exampleargument, exampleoption) -> None:  # The name of the function is used as name for the subcommand
	"""
	This is a subcommand example to the ##ID## command
	"""
	logger.trace("##ID## 'subcommand' subcommand")
	print(f"##ID## subcommand is called with values exampleargument={exampleargument} and exampleoption={exampleoption}")


# This class keeps track of the plugins meta-information
class CustomPlugin(OPSICLIPlugin):
	id: str = "##ID##"  # pylint: disable=invalid-name
	name: str = "##NAME##"
	description: str = __description__
	version: str = __version__
	cli = cli
