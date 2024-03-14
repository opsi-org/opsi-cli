"""
opsi-cli basic command line interface for opsi

config plugin
"""

from urllib.parse import urlparse

import rich_click as click  # type: ignore[import]
from click.shell_completion import CompletionItem  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli.config import ConfigValueSource, config
from opsicli.io import list_attributes, prompt, write_output
from opsicli.plugin import OPSICLIPlugin
from opsicli.types import OPSIService, Password
from opsicli.utils import get_subcommand_sequence
from plugins.config.python.metadata import command_metadata

__version__ = "0.1.0"

logger = get_logger("opsicli")


@click.group(name="config", short_help="Manage opsi-cli configuration")
@click.version_option(__version__, message="config plugin, version %(version)s")
@click.pass_context
def cli(ctx: click.Context) -> None:
	"""
	opsi-cli config command.
	This command is used to manage opsi-cli configuration.
	"""
	logger.trace("config command")

	if config.list_attributes:
		command = get_subcommand_sequence(ctx)
		metadata = command_metadata.get(command) if command is not None else None
		if metadata is not None:
			list_attributes(metadata)
			ctx.exit()


@cli.command(name="list", short_help="List configuration items")
def config_list() -> None:
	"""
	opsi-cli config list subcommand.
	"""
	metadata = command_metadata.get("list")

	data = []
	for item in sorted(config.get_config_items(), key=lambda x: x.name):
		data.append({"name": item.name, "type": item.type, "default": item.default, "value": item.value})

	write_output(data, metadata)


def complete_config_item_name(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[CompletionItem]:
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
	metadata = command_metadata.get("show")

	data = []
	item = config.get_config_item(name).as_dict()
	for attribute in ("name", "type", "multiple", "default", "description", "plugin", "group", "value"):
		data.append({"attribute": attribute, "value": item[attribute]})

	write_output(data, metadata)


@cli.command(name="set", short_help="Set configuration value")
@click.argument("key", type=str, shell_complete=complete_config_item_name)
@click.argument("value", type=str)
@click.option("--system", is_flag=True, default=False, help="If this is set, store new configuration value system-wide.")
def config_set(key: str, value: str, system: bool) -> None:
	"""
	Set a value for an configuration item.
	A system-wide setting overwrites the default value of the configuration object.
	A user-specific configuration has priority over a system-wide setting.
	"""
	logger.notice("Setting config %s to %s", key, value)
	source = ConfigValueSource.CONFIG_FILE_SYSTEM if system else ConfigValueSource.CONFIG_FILE_USER
	config.get_config_item(key).set_value(value, source)
	config.write_config_files(sources=[source])


@cli.command(name="unset", short_help="Unset configuration value")
@click.argument("key", type=str, shell_complete=complete_config_item_name)
@click.option("--system", is_flag=True, default=False, help="If this is set, remove value from system-wide configuration.")
def config_unset(key: str, system: bool) -> None:
	"""
	Remove configured value for an configuration item.
	If a user-specific value is deleted, the system-wide setting applies again.
	If no system-wide setting exists, the default value of the configuration item applies.
	"""

	logger.notice("Unsetting config %s ", key)
	source = ConfigValueSource.CONFIG_FILE_SYSTEM if system else ConfigValueSource.CONFIG_FILE_USER
	config.get_config_item(key).set_value(config.get_config_item(key).get_default())
	config.write_config_files(sources=[source], skip_keys=[key])


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
	metadata = command_metadata.get("service_list")

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
@click.option("--system", is_flag=True, type=bool, required=False, default=False)
def service_add(
	url: str | None = None,
	name: str | None = None,
	username: str | None = None,
	password: str | None = None,
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
	if config.get_config_item("service").is_default():
		logger.info("Setting config service to %r as no value was set", name)
		config.get_config_item("service").set_value(name, source)
	config.write_config_files(sources=[source])


@service.command(name="remove", short_help="Remove an opsi service")
@click.argument("name", type=str, required=False)
@click.option("--system", is_flag=True, type=bool, required=False, default=False)
def service_remove(
	name: str | None = None,
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


@service.command(name="set-default", short_help="set opsi-service default")
@click.argument("name", type=str, required=False)
@click.option("--system", is_flag=True, type=bool, required=False, default=False)
def service_set_default(
	name: str | None = None,
	system: bool = False,
) -> None:
	"""
	opsi-cli config service set-default subcommand.
	"""
	source = ConfigValueSource.CONFIG_FILE_SYSTEM if system else ConfigValueSource.CONFIG_FILE_USER
	config_item = config.get_config_item("services")
	values = config_item.get_values(value_only=False, sources=[source])
	names = sorted([val.value.name for val in values])

	if name:
		if name not in names:
			raise ValueError(f"Service {name} not found in {'system' if system else 'user'} configuration")
		config.get_config_item("service").set_value(name)
	else:
		# Name not specified: reset to default
		config.get_config_item("service").set_value(config.get_config_item("service").get_default())
	config.write_config_files(sources=[source])


class ConfigPlugin(OPSICLIPlugin):
	name: str = "Config"
	description: str = "Manage opsi-cli configuration"
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
