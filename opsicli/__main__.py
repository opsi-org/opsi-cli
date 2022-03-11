# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

Main command
"""

import sys
import pathlib
from typing import Any, List, Dict, Optional, Sequence
from types import ModuleType
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
from click.exceptions import ClickException, Abort
from click.shell_completion import CompletionItem
import rich_click as click  # type: ignore[import]
from rich_click.rich_click import rich_format_error, rich_abort_error, rich_format_help  # type: ignore[import]

from opsicommon.logging import logger, logging_config, DEFAULT_FORMAT, DEFAULT_COLORED_FORMAT  # type: ignore[import]

from opsicli import plugin, prepare_cli_paths, prepare_context, __version__
from opsicli.config import config
from opsicli.types import TypeLogLevel

click.rich_click.USE_RICH_MARKUP = True
click.rich_click.MAX_WIDTH = 140
click.rich_click.OPTION_GROUPS = {"opsi-cli": []}
for group, items in config.get_items_by_group().items():
	if not group:
		continue
	options = []
	for item in items:
		if item.plugin:
			continue
		options.append(f"--{item.name.replace('_', '-')}")
	if options:
		click.rich_click.OPTION_GROUPS["opsi-cli"].append({"name": f"{group} options", "options": options})


# https://click.palletsprojects.com/en/7.x/commands/#custom-multi-commands
class OpsiCLI(click.MultiCommand):
	def __init__(self, *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)
		self.plugin_modules: Dict[str, ModuleType] = {}

	def main(
		self,
		args: Optional[Sequence[str]] = None,
		prog_name: Optional[str] = None,
		complete_var: Optional[str] = None,
		standalone_mode: bool = False,
		**extra: Any,
	) -> Any:
		try:
			return super().main(args, prog_name, complete_var, standalone_mode, **extra)
		except ClickException as err:
			if not config.color:
				raise
			rich_format_error(err)
			sys.exit(err.exit_code)
		except Abort:
			if not config.color:
				raise
			rich_abort_error()
			sys.exit(1)

	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		if not config.color:
			return super().format_help(ctx, formatter)
		return rich_format_help(self, ctx, formatter)

	def register_plugins(self, ctx: click.Context) -> None:
		prepare_cli_paths()
		prepare_context(ctx)

		logger.debug("Initializing plugins from dir %r", config.plugin_dir)
		for dirname in config.plugin_dir.iterdir():
			try:
				self.load_plugin(ctx, dirname)
			except ImportError as import_error:
				logger.error("Could not load plugin from %r: %s", dirname, import_error, exc_info=True)
				raise  # continue

		self.plugin_modules["plugin"] = plugin

	def load_plugin(self, ctx: click.Context, dirname: Path) -> None:
		path = config.plugin_dir / dirname / "__init__.py"
		if not path.exists():
			raise ImportError(f"{config.plugin_dir / dirname!r} does not have __init__.py")
		spec = spec_from_file_location("temp", path)
		if not spec:
			raise ImportError(f"{config.plugin_dir / dirname / '__init__.py'!r} is not a valid python module")
		new_plugin = module_from_spec(spec)
		if not spec.loader:
			raise ImportError(f"{config.plugin_dir / dirname / '__init__.py'!r} spec does not have valid loader")
		spec.loader.exec_module(new_plugin)
		try:
			name = new_plugin.get_plugin_info()["name"]
		except (AttributeError, KeyError) as error:
			raise ImportError(
				f"{config.plugin_dir / dirname!r} does not have a valid get_plugin_info method (key name required)"
			) from error
		self.plugin_modules[name] = new_plugin

		logger.debug("Adding plugin %r", name)
		# add reference to plugin modules into context to access it in plugin management
		ctx.obj["plugins"][name] = config.plugin_dir / dirname

	def list_commands(self, ctx: click.Context) -> List[str]:
		if not self.plugin_modules:
			self.register_plugins(ctx)
		return sorted(self.plugin_modules.keys())

	def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command:
		if cmd_name not in self.plugin_modules:
			self.register_plugins(ctx)
			if cmd_name not in self.plugin_modules:
				raise ValueError(f"Invalid command {cmd_name!r}")
		return self.plugin_modules[cmd_name].cli


class LogLevel(click.ParamType):
	def convert(self, value: Any, param: Optional[click.Parameter], ctx: Optional[click.Context]) -> int:
		try:
			value = TypeLogLevel(value)
		except ValueError as err:
			self.fail(str(err), param, ctx)
		return value

	def get_metavar(self, param: click.Parameter) -> str:
		return "LOG_LEVEL"

	def shell_complete(self, ctx: click.Context, param: click.Parameter, incomplete: str) -> List[CompletionItem]:
		completion_items = []
		try:
			completion_items = [CompletionItem(min(9, max(0, int(incomplete))))]
		except ValueError:
			for name in TypeLogLevel.possible_level_names:
				if name.startswith(incomplete.lower()):
					completion_items.append(name)
		return completion_items

	def __repr__(self) -> str:
		return "LOG_LEVEL"


@click.command(cls=OpsiCLI)
@click.pass_context
@click.version_option(f"{__version__}", message="opsi-cli version %(version)s")
@click.option(
	"--config-file",
	"-c",
	type=click.Path(dir_okay=False),
	callback=config.process_option,
	metavar="CONFIG_FILE",
	is_eager=True,
	expose_value=False,
	help=config.get_description("config_file"),
	default=config.get_default("config_file"),
	show_default=True,
)
@click.option(
	"--log-file",
	type=click.Path(
		exists=False, file_okay=True, dir_okay=False, writable=True, resolve_path=True, allow_dash=True, path_type=pathlib.Path
	),
	callback=config.process_option,
	metavar="LOG_FILE",
	help=config.get_description("log_file"),
	default=config.get_default("log_file"),
)
@click.option(
	"--log-level-file",
	type=LogLevel(),
	callback=config.process_option,
	show_default=True,
	help=config.get_description("log_level_file"),
	default=config.get_default("log_level_file"),
)
@click.option(
	"--log-level-stderr",
	"-l",
	type=LogLevel(),
	callback=config.process_option,
	show_default=True,
	help=config.get_description("log_level_stderr"),
	default=config.get_default("log_level_stderr"),
)
@click.option(
	"--color/--no-color",
	is_eager=True,
	callback=config.process_option,
	help=config.get_description("color"),
	default=config.get_default("color"),
)
@click.option(
	"--service-url",
	type=str,
	callback=config.process_option,
	metavar="SERVICE_URL",
	help=config.get_description("service_url"),
	show_default=True,
	default=config.get_default("service_url"),
)
@click.option(
	"--username",
	"-u",
	envvar="OPSI_USERNAME",
	metavar="USERNAME",
	type=str,
	callback=config.process_option,
	default=config.get_default("username"),
	help=config.get_description("username"),
)
@click.option(
	"--password",
	"-p",
	envvar="OPSI_PASSWORD",
	metavar="PASSWORD",
	type=str,
	callback=config.process_option,
	default=config.get_default("password"),
	help=config.get_description("password"),
)
def main(  # pylint: disable=too-many-arguments
	ctx: click.Context,
	color: bool,
	log_level_stderr: int,
	log_file: pathlib.Path,
	log_level_file: int,
	service_url: str,
	username: str,
	password: str,
) -> None:
	"""
	opsi command line interface\n
	Plugins are dynamically loaded from a subfolder
	"""
	# print(color, log_level_stderr, log_file, log_level_file, service_url, username, password)
	logging_config(
		log_file=log_file,
		file_level=log_level_file,
		stderr_level=log_level_stderr,
		stderr_format=DEFAULT_COLORED_FORMAT if color else DEFAULT_FORMAT,
	)
	if not ctx.obj:  # stacked execution in pytest circumvents register_plugins -> explicit call here
		logger.notice("Explicitely calling register_plugins")
		assert isinstance(ctx.command, OpsiCLI)  # generic command does not have register_plugins
		ctx.command.register_plugins(ctx)
	ctx.obj.update({"username": username, "password": password, "service_url": service_url})
	logger.trace("cli was called")
