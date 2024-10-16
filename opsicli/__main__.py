# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

Main command
"""

import builtins

# pylint: disable=wrong-import-position
import re
import sys
from typing import Any, Sequence

from click.exceptions import Abort, ClickException  # type: ignore[import]
from click.shell_completion import CompletionItem  # type: ignore[import]
from opsicommon.exceptions import OpsiServiceConnectionError
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli import __version__, prepare_cli_paths
from opsicli.cache import cache
from opsicli.config import COMPLETION_MODE, config
from opsicli.plugin import plugin_manager
from opsicli.types import LogLevel as TypeLogLevel
from opsicli.types import OpsiCliRuntimeError

original_print = builtins.print

if not COMPLETION_MODE:
	import rich_click as click  # type: ignore[import,no-redef]
	from rich_click.rich_click import (  # type: ignore[import]
		_get_rich_formatter,
		rich_abort_error,
		rich_format_error,
		rich_format_help,
	)

	from opsicli.io import get_console
else:
	# Loads faster
	import click  # type: ignore[import,no-redef]

if not COMPLETION_MODE:
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

	from opsicommon.utils import patch_popen

	patch_popen()

logger = get_logger("opsicli")


# https://click.palletsprojects.com/en/8.1.x/commands/#custom-multi-commands
class OpsiCLI(click.MultiCommand):  # type: ignore
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
		except Exception as err:
			# Avoid gigantic traceback for known errors
			exc_type = type(err)
			exc_info = not issubclass(exc_type, (OpsiCliRuntimeError, OpsiServiceConnectionError))
			logger.error(err, exc_info=exc_info)

			additional_info = ""
			if issubclass(exc_type, OpsiServiceConnectionError) and not config.service:
				additional_info = "\nNo config service configured, use [bold cyan]opsi-cli config service add[/bold cyan]"

			if not isinstance(err, ClickException):
				err = ClickException(str(err))
			err.message += additional_info

			err_console = get_console(file=sys.stderr)
			if config.color:
				err.message = re.sub(r"\[/?metavar\]", "", err.message)
				formatter = _get_rich_formatter()
				formatter._console = err_console
				formatter.config.highlighter = lambda x: x  # type: ignore[assignment]
				if issubclass(exc_type, Abort):
					rich_abort_error()
				else:
					rich_format_error(err)
			else:
				if issubclass(exc_type, Abort):
					err_console.print("Aborted.")
				else:
					err_console.print(f"Error: {err}")

			sys.exit(err.exit_code)

		finally:
			cache.exit()

	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		# configs are evaluated lazily. Config files are only read on click processing option "config_file_system" and "config_file_user"
		# This does not happen if click realizes an argument (command) is missing
		config.read_config_files()
		if not config.color or "rich_format_help" not in globals():
			return super().format_help(ctx, formatter)
		return rich_format_help(self, ctx, formatter)

	def list_commands(self, ctx: click.Context) -> list[str]:
		logger.debug("list_commands")
		return sorted(plugin_manager.plugins)

	def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command:
		logger.debug("get_command %r", cmd_name)
		try:
			plugin = plugin_manager.load_plugin(cmd_name)
		except ModuleNotFoundError as err:
			raise ModuleNotFoundError(f"Invalid command {cmd_name!r} ({err})") from err
		if plugin.cli:
			return plugin.cli
		raise RuntimeError(f"Plugin {cmd_name} appears to be broken.")


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


def quiet_print(*args: Any, **kwargs: Any) -> None:
	"""
	Suppress builtins print if quiet mode is enabled.
	stderr output will only be suppressed if --hide-errors is used.
	"""
	if kwargs.get("file") == sys.stderr and not config.hide_errors:
		original_print(*args, **kwargs)


@click.command(cls=OpsiCLI)
@click.version_option(f"{__version__}", message="opsi-cli version %(version)s")
@config.get_click_option("config_file_system", is_eager=True, expose_value=False)
@config.get_click_option("config_file_user", is_eager=True, expose_value=False)
@config.get_click_option("log_file")
@config.get_click_option("log_level_file")
@config.get_click_option("log_level_stderr", short_option="-l")
@config.get_click_option("color", long_option="--color/--no-color", is_eager=True, envvar="NO_COLOR")
@config.get_click_option("interactive", long_option="--interactive/--non-interactive")
@config.get_click_option("quiet", is_flag=True, help=f"{config.get_description('quiet')}")
@config.get_click_option("hide_errors", is_flag=True, help=f"{config.get_description('hide_errors')}")
@config.get_click_option("output_format")
@config.get_click_option("output_file")
@config.get_click_option("input_file")
@config.get_click_option("metadata", long_option="--metadata/--no-metadata")
@config.get_click_option("header", long_option="--header/--no-header")
@config.get_click_option("attributes", show_default=False, help=f"{config.get_description('attributes')}. Comma separated list.")
@config.get_click_option(
	"list_attributes",
	expose_value=False,
	is_flag=True,
	default=False,
	help=f"{config.get_description('list_attributes')}",
)
@config.get_click_option("sort_by", help=f"{config.get_description('sort_by')}. Comma separated list.")
@config.get_click_option("service")
@config.get_click_option("username", short_option="-u")
@config.get_click_option("password", short_option="-p")
@config.get_click_option("totp", is_flag=True, help=f"{config.get_description('totp')}")
@config.get_click_option("dry_run", long_option="--dry-run/--no-dry-run")
def main(*args: str, **kwargs: str) -> None:
	"""
	opsi command line interface\n
	Plugins are dynamically loaded from a subfolder
	"""
	logger.debug("Main called")
	prepare_cli_paths()
	if config.quiet:
		logger.debug("Quiet mode enabled, disabling print")
		builtins.print = quiet_print
