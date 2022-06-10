"""
opsi-cli basic command line interface for opsi

config plugin
"""

from typing import List, Optional
from urllib.parse import urlparse

import rich_click as click  # type: ignore[import]
from click.shell_completion import CompletionItem  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.config import ConfigValueSource, config
from opsicli.io import prompt, write_output
from opsicli.plugin import OPSICLIPlugin
from opsicli.types import OPSIService, Password

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
	metadata = {
		"attributes": [
			{"id": "name", "description": "The service identifier", "identifier": True},
			{"id": "url", "description": "The base url of the opsi service"},
			{"id": "username", "description": "Username to use for authentication"},
			{"id": "password", "description": "Password to use for authentication"},
		]
	}
	data = []
	for item in sorted(config.services, key=lambda x: x.name):
		data.append({"name": item.name, "url": item.url, "username": item.username, "password": "*****" if item.password else ""})

	write_output(data, metadata)


@service.command(name="add", short_help="Add an opsi service")
@click.argument("url", type=str, required=False)
# @click.argument("name", type=str, required=False)
@click.option("--name", type=str, required=False, default=None)
@click.option("--username", type=str, required=False, default=None)
@click.option("--password", type=str, required=False, default=None)
@click.option("--system", type=bool, required=False, default=False)
def service_add(
	url: Optional[str] = None,
	name: Optional[str] = None,
	username: Optional[str] = None,
	password: Optional[str] = None,
	system: bool = False,
) -> None:
	"""
	opsi-cli config service add subcommand.
	"""
	interactive = False
	if not url:
		if not config.interactive:
			raise ValueError("No url specified")
		interactive = True
		url = str(prompt("Please enter the base url of the opsi service", default="https://localhost:4447"))

	ourl = urlparse(url)
	if not name:
		name = str(ourl.hostname)
		if interactive:
			name = str(prompt("Please enter a name for the service", default=name))

	if not username and interactive:
		username = str(prompt("Enter the username to use for authentication (optional)")) or None

	if not password and interactive:
		password = str(prompt("Enter the password to use for authentication (optional)", password=True)) or None

	new_service = OPSIService(name=name, url=url, username=username, password=Password(password))

	source = ConfigValueSource.CONFIG_FILE_SYSTEM if system else ConfigValueSource.CONFIG_FILE_USER
	config.get_config_item("services").add_value(new_service, source)
	config.write_config_files(sources=[source])


@service.command(name="remove", short_help="Remove an opsi service")
@click.argument("name", type=str, required=False)
@click.option("--system", type=bool, required=False, default=False)
def service_remove(
	name: Optional[str] = None,
	system: bool = False,
) -> None:
	"""
	opsi-cli config service remove subcommand.
	"""
	source = ConfigValueSource.CONFIG_FILE_SYSTEM if system else ConfigValueSource.CONFIG_FILE_USER
	config_item = config.get_config_item("services")
	values = config_item.get_values(value_only=False, sources=[source])
	names = sorted([val.value.name for val in values])

	if not name:
		if not config.interactive:
			raise ValueError("No name specified")
		if not names:
			raise ValueError("No services specified")
		name = str(prompt("Please enter a name for the service", choices=names))

	if name not in names:
		raise ValueError(f"Service {name} not found in {'system' if system else 'user'} configuration")

	for val in values:
		if val.value.name == name:
			config_item.remove_value(val)
			config.write_config_files(sources=[source])
			break


class ConfigPlugin(OPSICLIPlugin):
	id: str = "config"  # pylint: disable=invalid-name
	name: str = "Config"
	description: str = "Manage opsi-cli configuration"
	version: str = __version__
	cli = cli
	flags = ["protected"]
