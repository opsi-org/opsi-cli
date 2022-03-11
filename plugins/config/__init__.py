"""
opsi-cli basic command line interface for opsi

config plugin
"""

from typing import Any, Dict
from rich.table import Table
import rich_click as click  # type: ignore[import]

from opsicommon.logging import logger  # type: ignore[import]

from opsicli import get_console
from opsicli.config import config

__version__ = "0.1.0"


def get_plugin_info() -> Dict[str, Any]:
	return {"name": "config", "description": "Manage opsi-cli configuration", "version": __version__}


@click.group(name="config", short_help="Manage opsi-cli configuration")
@click.version_option(__version__, message="config plugin, version %(version)s")
def cli() -> None:  # pylint: disable=unused-argument
	"""
	opsi-cli config command.
	This command is used to manage opsi-cli configuration.
	"""
	logger.trace("config command")


@cli.command(short_help="Show current configuration")
def show() -> None:
	"""
	opsi-cli config show subcommand.
	"""

	table = Table()

	table.add_column("Name", style="cyan", no_wrap=True)
	table.add_column("Type")
	table.add_column("Default")
	table.add_column("Value", style="green")

	for item in sorted(config.get_config_items(), key=lambda x: x.name):
		table.add_row(item.name, item.type.__name__, item.default_repr(), item.value_repr())

	get_console().print(table)
