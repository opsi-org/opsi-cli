"""
template for opsi-cli plugins
"""

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli.io import write_output
from opsicli.plugin import OPSICLIPlugin

from .worker import default_health_check

__version__ = "0.1.0"  # Use this field to track the current version number
__description__ = ""


logger = get_logger("opsicli")


@click.group(name="support", short_help="Custom plugin support")
@click.version_option(__version__, message="opsi-cli plugin support, version %(version)s")
def cli() -> None:  # The docstring is used in opsi-cli support --help
	""" """
	logger.trace("support command")


@cli.command()
def health_check() -> None:
	data, metadata = default_health_check()

	write_output(data=data, metadata=metadata)


# This class keeps track of the plugins meta-information
class CustomPlugin(OPSICLIPlugin):
	id: str = "support"  # pylint: disable=invalid-name
	name: str = "support"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = []
