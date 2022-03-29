"""
opsi-cli basic command line interface for opsi

config plugin
"""

from typing import List

import rich_click as click  # type: ignore[import]
from click.shell_completion import CompletionItem
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.config import config
from opsicli.io import write_output
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
		"attributes": [
			{"id": "name", "description": "Name of configuration item", "identifier": True},
			{"id": "type", "description": "Data type"},
			{"id": "default", "description": "Default value"},
			{"id": "value", "description": "Current value"},
		]
	}
	data = []
	for item in sorted(config.get_config_items(), key=lambda x: x.name):
		data.append({"name": item.name, "type": item.type, "default": item.default, "value": item.value})

	write_output(data, metadata)


def complete_config_item_name(
	ctx: click.Context, param: click.Parameter, incomplete: str  # pylint: disable=unused-argument
) -> List[CompletionItem]:
	items = []
	for item in config.get_config_items():
		if item.name.startswith(incomplete):
			items.append(CompletionItem(item.name))
	return items


@cli.command(short_help="Show configuration item details")
@click.argument("name", type=str, shell_complete=complete_config_item_name)
def show(name: str) -> None:
	"""
	opsi-cli config show subcommand.
	"""
	metadata = {
		"attributes": [
			{"id": "attribute", "description": "Name of the configuration item attribute", "identifier": True},
			{"id": "value", "description": "Attribute value"},
		]
	}
	data = []
	item = config.get_config_item(name).as_dict()
	for attribute in ("name", "type", "multiple", "default", "description", "plugin", "group", "value"):
		data.append({"attribute": attribute, "value": item[attribute]})

	write_output(data, metadata)


class ConfigPlugin(OPSICLIPlugin):
	id: str = "config"  # pylint: disable=invalid-name
	name: str = "Config"
	description: str = "Manage opsi-cli configuration"
	version: str = __version__
	cli = cli
