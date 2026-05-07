# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
template for opsi-cli plugins
"""

import rich_click as click
from opsi.logging import get_logger

from opsicli.io import OutputType, console_print
from opsicli.plugin import OPSICLIPlugin

__version__ = "{{VERSION}}"  # Use this field to track the current version number
__description__ = "{{DESCRIPTION}}"


logger = get_logger("opsicli")


@click.group(name="{{ID}}", short_help="Custom plugin {{NAME}}")
@click.version_option(__version__, message="opsi-cli plugin {{NAME}}, version %(version)s")
def cli() -> None:  # The docstring is used in opsi-cli {{ID}} --help
	"""
	{{DESCRIPTION}}
	"""
	logger.trace("{{ID}} command")


@cli.command(short_help="Some example subcommand")
@click.argument("exampleargument", nargs=1, default="defaultvalue", type=str)
@click.option("--exampleoption", "-o", help="example for an option", is_flag=True, default=False)
def subcommand(exampleargument: str, exampleoption: bool) -> None:  # The name of the function is used as name for the subcommand
	"""
	This is a subcommand example to the {{ID}} command
	"""
	logger.trace("{{ID}} 'subcommand' subcommand")
	console_print(f"{{ID}} subcommand is called with values exampleargument={exampleargument}", output_type=OutputType.DATA)
	if exampleoption:
		console_print("exampleoption was used.", output_type=OutputType.WARNING_MESSAGE)


# This class keeps track of the plugins meta-information
class CustomPlugin(OPSICLIPlugin):
	name: str = "{{NAME}}"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = []
