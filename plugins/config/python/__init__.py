"""
opsi-cli basic command line interface for opsi

config plugin
"""

from typing import List, Optional
from urllib.parse import urlparse

import rich_click as click  # type: ignore[import]
from click.shell_completion import CompletionItem
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.config import config
from opsicli.io import write_output
from opsicli.plugin import OPSICLIPlugin
from opsicli.types import OPSIService

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
def config_list() -> None:
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


@cli.command(name="show", short_help="Show configuration item details")
@click.argument("name", type=str, shell_complete=complete_config_item_name)
def config_show(name: str) -> None:
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


@cli.group(short_help="Configuration of opsi services")
def service() -> None:
	"""
	opsi-cli config service subcommand.
	"""


@service.command(name="list", short_help="List configured opsi services")
def service_list() -> None:
	"""
	opsi-cli config service list subcommand.
	"""
	print(config.services)


@service.command(name="add", short_help="Add an opsi service")
@click.argument("url", type=str, required=False)
@click.argument("name", type=str, required=False)
def service_add(url: Optional[str] = None, name: Optional[str] = None) -> None:
	"""
	opsi-cli config service add subcommand.
	"""
	if not url:
		if not config.interactive:
			raise ValueError("No url specified")
		url = click.prompt("Please enter the base url of the opsi service", type=str, default="https://localhost:4447")
	ourl = urlparse(url)
	if not name:
		name = ourl.hostname
		if config.interactive:
			name = click.prompt("Please enter a name for the service", type=str, default=name)

	config.get_config_item("services").add_value(OPSIService(name, url))


class ConfigPlugin(OPSICLIPlugin):
	id: str = "config"  # pylint: disable=invalid-name
	name: str = "Config"
	description: str = "Manage opsi-cli configuration"
	version: str = __version__
	cli = cli
