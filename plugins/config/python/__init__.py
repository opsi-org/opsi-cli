"""
opsi-cli basic command line interface for opsi

config plugin
"""

from pathlib import Path
from typing import Any, Dict

import rich_click as click  # type: ignore[import]

from opsicommon.logging import logger  # type: ignore[import]

from opsicli import write_output
from opsicli.config import config
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"


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
	meta_data = {
		"columns": [
			{"id": "name", "title": "Name", "identifier": True},
			{"id": "type", "title": "Type"},
			{"id": "default", "title": "Default"},
			{"id": "value", "title": "Value"},
		]
	}
	data = []
	for item in sorted(config.get_config_items(), key=lambda x: x.name):
		data.append({"name": item.name, "type": item.type, "default": item.default, "value": item.value})

	write_output(meta_data, data)


class ConfigPlugin(OPSICLIPlugin):
	id: str = "config"  # pylint: disable=invalid-name
	name: str = "Config"
	description: str = "Manage opsi-cli configuration"
	version: str = __version__
	cli = cli
