# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

Main command
"""

import re
import sys
from typing import Any, Sequence

import rich_click as click  # type: ignore[import]
from click.exceptions import Abort, ClickException  # type: ignore[import]
from click.shell_completion import CompletionItem  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]
from rich_click.rich_click import (  # type: ignore[import]
	rich_abort_error,
	rich_format_error,
	rich_format_help,
)

from opsicli import __version__, prepare_cli_paths
from opsicli.cache import cache
from opsicli.config import config
from opsicli.plugin import plugin_manager
from opsicli.types import LogLevel as TypeLogLevel

click.rich_click.USE_RICH_MARKUP = True
click.rich_click.MAX_WIDTH = 140

# https://rich.readthedocs.io/en/stable/style.html
# https://rich.readthedocs.io/en/stable/appendix/colors.html#appendix-colors
click.rich_click.STYLE_USAGE = "bold cyan3"
click.rich_click.STYLE_OPTION = "bold cyan"
click.rich_click.STYLE_SWITCH = "bold light_sea_green"
click.rich_click.STYLE_METAVAR = "cyan3"
click.rich_click.STYLE_ERRORS_SUGGESTION = ""

click.rich_click.OPTION_GROUPS = {"opsi-cli": []}
for group, items in config.get_items_by_group().items():
	if not group:
		continue
	options = []
	for item in items:
		if item.plugin:
			continue
		options.append(f"--{item.name.replace('_', '-')}")
	if group == "General":
		options.extend(["--help", "--version"])
	if options:
		click.rich_click.OPTION_GROUPS["opsi-cli"].append({"name": f"{group} options", "options": options})


logger = get_logger("opsicli")


# https://click.palletsprojects.com/en/7.x/commands/#custom-multi-commands
class OpsiCLI(click.MultiCommand):
	def main(
		self,
		args: Sequence[str] | None = None,
		prog_name: str | None = None,
		complete_var: str | None = None,
		standalone_mode: bool = False,
		**extra: Any,
	) -> Any:
		try:
			return super().main(args, prog_name, complete_var, standalone_mode, **extra)
		except Abort:
			if config.color:
				rich_abort_error()
			else:
				sys.stderr.write("Aborted.\n")
			sys.exit(1)
		except Exception as err:  # pylint: disable=broad-except
			logger.error(err, exc_info=True)
			if not isinstance(err, ClickException):
				err = ClickException(str(err))
			if config.color:
				err.message = re.sub(r"\[/?metavar\]", "", err.message)
				rich_format_error(err)
			else:
				sys.stderr.write(f"Error: {err}\n")
			sys.exit(err.exit_code)
		finally:
			cache.exit()

	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		if not config.color:
			return super().format_help(ctx, formatter)
		return rich_format_help(self, ctx, formatter)

	def list_commands(self, ctx: click.Context) -> list[str]:
		logger.debug("list_commands")
		return sorted(plugin_manager.plugins)

	def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command:
		logger.debug("get_command %r", cmd_name)
		plugin = plugin_manager.load_plugin(cmd_name)
		if plugin.cli and plugin.cli.name == cmd_name:
			return plugin.cli
		raise ValueError(f"Invalid command {cmd_name!r}")


class LogLevel(click.ParamType):
	def shell_complete(self, ctx: click.Context, param: click.Parameter, incomplete: str) -> list[CompletionItem]:
		completion_items = []
		try:
			completion_items = [CompletionItem(min(9, max(0, int(incomplete))))]
		except ValueError:
			for name in TypeLogLevel.possible_values:
				if name.startswith(incomplete.lower()):
					completion_items.append(CompletionItem(name))
		return completion_items


@click.command(cls=OpsiCLI)
@click.version_option(f"{__version__}", message="opsi-cli version %(version)s")
@config.get_click_option("config_file_system", is_eager=True, expose_value=False)
@config.get_click_option("config_file_user", is_eager=True, expose_value=False)
@config.get_click_option("log_file")
@config.get_click_option("log_level_file")
@config.get_click_option("log_level_stderr", short_option="-l")
@config.get_click_option("color", is_eager=True, envvar="NO_COLOR")
@config.get_click_option("interactive", long_option="--interactive/--non-interactive")
@config.get_click_option("output_format")
@config.get_click_option("output_file")
@config.get_click_option("input_file")
@config.get_click_option("metadata")
@config.get_click_option("header")
@config.get_click_option("attributes", show_default=False, help=f"{config.get_description('attributes')}. Comma separated list.")
@config.get_click_option("service")
@config.get_click_option("username", short_option="-u")
@config.get_click_option("password", short_option="-p")
@config.get_click_option("dry_run", is_flag=True)
def main(*args: str, **kwargs: str) -> None:  # pylint: disable=unused-argument
	"""
	opsi command line interface\n
	Plugins are dynamically loaded from a subfolder
	"""
	logger.debug("Main called")
	prepare_cli_paths()
