# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

import importlib
import os
import re
from typing import Any, Optional

from rich.panel import Panel
from rich.text import Text

from opsicli import logger
from opsicli.config import config
from opsicli.io import OutputType, console_print, get_console, list_attributes
from opsicli.plugin import plugin_manager

COMPLETION_MODE = "_OPSI_CLI_COMPLETE" in os.environ or "_OPSI_CLI_EXE_COMPLETE" in os.environ

if COMPLETION_MODE:
	import click
else:
	import rich_click as click
	import rich_click.rich_click as rich_click
	from rich_click.rich_click import rich_format_help

	rich_click.STYLE_OPTIONS_PANEL_BORDER = "bold"
	rich_click.OPTIONS_PANEL_TITLE = "[bold cyan]OPTIONS[/bold cyan]"


_METAVAR_RE = re.compile(r"\[metavar\](.*?)\[/metavar\]")
_config_loaded = False


def _get_all_parent_options(ctx: click.Context) -> list[tuple[str, list[click.Option]]]:
	result = []
	current = ctx.parent
	while current:
		cmd = current.command
		opts = [p for p in getattr(cmd, "params", []) if isinstance(p, click.Option)]
		result.append((cmd.name or cmd.__class__.__name__, opts))
		current = current.parent if isinstance(current.parent, click.Context) else None
	result.reverse()
	return result


def _format_option_lines(opts: list[click.Option], col_width: int, use_rich: bool, console: Any) -> list[str]:
	lines = []
	console_width = getattr(console, "width", 100)
	wrap_width = max(20, console_width - col_width)
	for p in opts:
		opts_str = f"[cyan]{', '.join(p.opts)}[/cyan]".ljust(col_width) if use_rich else ", ".join(p.opts).ljust(col_width)
		help_str = p.help or ""
		if not use_rich:
			help_str = _METAVAR_RE.sub(r"\1", help_str)
		help_text = Text.from_markup(help_str)
		wrapped_lines = Text.wrap(help_text, console, width=wrap_width)
		for i, line in enumerate(wrapped_lines):
			if use_rich:
				lines.append(f"{opts_str if i == 0 else ' ' * (col_width - 13)}[grey50]{line}[/grey50]")
			else:
				lines.append(f"{opts_str if i == 0 else ' ' * col_width}{line}")
	return lines


def _format_help(obj: Any, ctx: click.Context, formatter: click.HelpFormatter) -> None:
	global _config_loaded
	if not _config_loaded:
		config.read_config_files()
		_config_loaded = True
	parent_opts_by_cmd = _get_all_parent_options(ctx)
	use_rich = config.color and "rich_format_help" in globals()
	console = get_console(output_type=OutputType.DATA)

	for cmd_name, opts in parent_opts_by_cmd:
		if not opts:
			continue
		display_cmd_name = "Global" if cmd_name.lower() == "main" else cmd_name.capitalize()
		col_width = 44 if use_rich else max(20, *(len(opt) + 5 for p in opts for opt in p.opts))
		lines = _format_option_lines(opts, col_width, use_rich, console)
		if use_rich:
			console_print(
				Panel(
					"\n".join(lines),
					title=f"[bold cyan]{display_cmd_name.upper()} OPTIONS[/bold cyan]",
					title_align="left",
					border_style="grey50",
					padding=(0, 1),
				),
				output_type=OutputType.DATA,
			)
		else:
			formatter.write(f"\n{display_cmd_name.upper()} OPTIONS:\n")
			for line in lines:
				formatter.write(f"  {line}\n")

	custom_usage = obj.get_usage(ctx)

	if use_rich:

		def _custom_get_rich_usage(obj: Any, ctx: click.Context, formatter: click.HelpFormatter) -> None:
			formatter = rich_click._get_rich_formatter(formatter)
			config = formatter.config
			console = formatter.console

			class UsageHighlighter(rich_click.RegexHighlighter):
				highlights = [
					r"(?P<argument>\[.*?\])",
				]

			usage_highlighter = UsageHighlighter()

			usage_str = custom_usage
			if usage_str.lower().startswith("usage:"):
				usage_str = usage_str[len("usage:") :].strip()

			console.print(
				rich_click.Padding(
					rich_click.Columns(
						(
							rich_click.Text("Usage:", style=config.style_usage),
							usage_highlighter(usage_str),
						)
					),
					1,
				),
			)

		rich_click.get_rich_usage = _custom_get_rich_usage  # type: ignore[invalid-assignment]
		rich_format_help(obj, ctx, formatter)

	else:
		formatter.write("\n" + "-" * 100 + "\n\n")
		formatter.write(f"\n{custom_usage}\n")
		type(obj).format_usage = lambda self, ctx, formatter: None
		super(type(obj), obj).format_help(ctx, formatter)


def _get_usage(ctx: click.Context) -> str:
	cls = type(ctx.command)
	assert issubclass(cls, click.Command)
	orig_usage = super(cls, ctx.command).get_usage(ctx)
	match = re.match(r"(Usage:\s*)(.*)", orig_usage)
	if not match:
		return orig_usage

	prefix, usage_body = match.groups()
	parts = usage_body.split()

	command_path: list[tuple[str, bool]] = []
	current: Optional[click.Context] = ctx
	while current:
		cmd = current.command
		if cmd.name:
			command_path.insert(0, (cmd.name, isinstance(cmd, click.Group)))
		current = current.parent

	if parts and parts[0] in ("opsi-cli", "main"):
		parts.insert(1, "[GLOBAL OPTIONS]")

	for name, is_group in command_path[:-1]:
		if is_group and name in parts:
			parts.insert(parts.index(name) + 1, f"[{name.upper()} OPTIONS]")

	return f"{prefix}{' '.join(parts)}"


# Assemble command sequence and load module/metadata.
# If metadata exists, output it.
def _handle_list_attributes_flag(ctx: click.Context):
	raw_arg_sequence = ctx.command_path.split(" ")[1:]
	plugin_name = raw_arg_sequence[0].replace("-", "_")
	command_sequence = "_".join(raw_arg_sequence)
	module = importlib.import_module(f"plugins.{plugin_name}.python.metadata")
	COMMAND_METADATA = getattr(module, "COMMAND_METADATA")
	metadata = COMMAND_METADATA.get(command_sequence)
	if not metadata:
		raise click.UsageError(f"ERROR: The command 'opsi-cli {' '.join(raw_arg_sequence)}' does not support --list-attributes. Aborting")

	list_attributes(metadata)
	ctx.exit()


def _handle_dry_run_flag(ctx: click.Context):
	if not hasattr(ctx.command.callback, "is_dry_run_handled"):
		raise click.UsageError(f"The command '{ctx.command_path}' does not support --dry-run. Aborting.")

	warning_message = "WARNING: Operating in dry-run mode - no actions will be performed."
	console_print(f"{warning_message}\n", output_type=OutputType.WARNING_MESSAGE)
	logger.warning(warning_message)


# returns the command_sequence with "_" as separators and the corresponding function
# e.g. {"datastore_config-state_list": <function  at 0xfe12979w98d>}
# in short {path: function}
def _get_opsi_commands_and_functions() -> dict[str, Any]:
	commands_dict = {}

	def walk_commands(command, prefix=""):
		if prefix:
			current_path = f"{prefix}_{command.name}".strip()
		else:
			current_path = f"{command.name}".strip()
		# only save command, if the lenght is > 1
		if command.callback and prefix:
			commands_dict[current_path] = command.callback

		if isinstance(command, click.Group):
			for sub_command in command.commands.values():
				walk_commands(sub_command, current_path)

	for plugin_id in sorted(plugin_manager.plugins):
		plugin = plugin_manager.load_plugin(plugin_id)
		if plugin.cli:
			walk_commands(plugin.cli)

	return commands_dict


class OPSICLICommand(click.Command):
	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		_format_help(self, ctx, formatter)

	def get_usage(self, ctx: click.Context) -> str:
		return _get_usage(ctx)

	# Why in OPSICLICommand and not OPSICLIGroup?
	# - This method is called last: only arguments and options can follow after a command
	def parse_args(self, ctx: click.Context, args):
		# only check for dry-run and list-atteributes if --help was not set
		if "--help" in args or "-h" in args:
			return super().parse_args(ctx, args)

		# if dry-run or list-attributes are set: special side-effects
		# parsing is stopped afterwards, command will not be executed
		if config.dry_run:
			_handle_dry_run_flag(ctx)
		if config.list_attributes:
			_handle_list_attributes_flag(ctx)

		# execute command as usual
		return super().parse_args(ctx, args)


class OPSICLIGroup(click.Group):
	def add_command(self, cmd: click.Command, name: Optional[str] = None) -> None:
		if isinstance(cmd, click.Group) and not isinstance(cmd, OPSICLIGroup):
			cmd.__class__ = OPSICLIGroup
		elif not isinstance(cmd, OPSICLICommand):
			cmd.__class__ = OPSICLICommand
		super().add_command(cmd, name)

	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		_format_help(self, ctx, formatter)

	def get_usage(self, ctx: click.Context) -> str:
		return _get_usage(ctx)

	def parse_args(self, ctx: click.Context, args):
		return super().parse_args(ctx, args)
