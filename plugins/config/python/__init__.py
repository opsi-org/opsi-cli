"""
opsi-cli basic command line interface for opsi

config plugin
"""

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


@cli.command(name="list", short_help="List configuration items")
def list_() -> None:
	"""
	opsi-cli config list subcommand.
	"""
	metadata = {
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

	write_output(metadata, data)


@cli.command(short_help="Show configuration item details")
@click.argument("name", type=str)
def show(name: str) -> None:
	"""
	opsi-cli config show subcommand.
	"""
	metadata = {
		"columns": [
			{"id": "attribute", "title": "Attribute", "identifier": True},
			{"id": "value", "title": "Value"},
		]
	}
	data = []
	item = config.get_config_item(name).dict()
	for attribute in ("name", "type", "multiple", "default", "description", "plugin", "group", "value"):
		data.append({"attribute": attribute, "value": item[attribute]})

	write_output(metadata, data)


class ConfigPlugin(OPSICLIPlugin):
	id: str = "config"  # pylint: disable=invalid-name
	name: str = "Config"
	description: str = "Manage opsi-cli configuration"
	version: str = __version__
	cli = cli
