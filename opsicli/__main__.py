# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

Main command
"""

import sys
import pathlib
from typing import Any, List, Optional, Sequence

from click.exceptions import ClickException, Abort
from click.shell_completion import CompletionItem
import rich_click as click  # type: ignore[import]
from rich_click.rich_click import rich_format_error, rich_abort_error, rich_format_help  # type: ignore[import]

from opsicommon.logging import logger  # type: ignore[import]

from opsicli import prepare_cli_paths, __version__
from opsicli.config import config
from opsicli.types import LogLevel as TypeLogLevel
from opsicli.plugin import plugin_manager

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
		except Abort:
			if not config.color:
				raise
			rich_abort_error()
			sys.exit(1)
		except Exception as err:  # pylint: disable=broad-except
			logger.error(err, exc_info=True)
			if not isinstance(err, ClickException):
				err = ClickException(str(err))
			if not config.color:
				raise
			rich_format_error(err)
			sys.exit(err.exit_code)

	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		if not config.color:
			return super().format_help(ctx, formatter)
		return rich_format_help(self, ctx, formatter)

	def list_commands(self, ctx: click.Context) -> List[str]:
		plugin_manager.load_plugins()
		return sorted([plugin.cli.name for plugin in plugin_manager.plugins if plugin.cli])  # type: ignore[attr-defined]

	def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command:
		plugin_manager.load_plugins()
		for plugin in plugin_manager.plugins:
			if plugin.cli and plugin.cli.name == cmd_name:
				return plugin.cli
		raise ValueError(f"Invalid command {cmd_name!r}")


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
def main(ctx: click.Context, *args, **kwargs) -> None:  # pylint: disable=unused-argument
	"""
	opsi command line interface\n
	Plugins are dynamically loaded from a subfolder
	"""
	logger.debug("main was called")
	prepare_cli_paths()
	# if not ctx.obj:  # stacked execution in pytest circumvents load_plugins -> explicit call here
	# 	logger.notice("Explicitly calling load_plugins")
	# 	assert isinstance(ctx.command, OpsiCLI)  # generic command does not have load_plugins
	# 	plugin_manager.load_plugins()
