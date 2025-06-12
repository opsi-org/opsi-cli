import os
import re
from typing import Any, Optional

from rich.panel import Panel
from rich.text import Text
from rich_click.rich_click import rich_format_help

from opsicli.config import config
from opsicli.io import OutputType, console_print, get_console

COMPLETION_MODE = "_OPSI_CLI_COMPLETE" in os.environ or "_OPSI_CLI_EXE_COMPLETE" in os.environ

if COMPLETION_MODE:
	import click
else:
	import rich_click as click  # type: ignore[no-redef]


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
	for p in opts:
		opts_str = f"[cyan]{', '.join(p.opts)}[/cyan]".ljust(col_width) if use_rich else ", ".join(p.opts).ljust(col_width)
		help_str = p.help or ""
		if not use_rich:
			help_str = _METAVAR_RE.sub(r"\1", help_str)
		help_text = Text.from_markup(help_str)
		wrapped_lines = Text.wrap(help_text, console, width=100 - col_width)
		for i, line in enumerate(wrapped_lines):
			indent = col_width - (13 if use_rich else 0)
			prefix = opts_str if i == 0 else " " * indent
			lines.append(f"{prefix}[grey50]{line}[/grey50]") if use_rich else lines.append(f"{prefix}{line}")
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
					title=f"{display_cmd_name} options",
					title_align="left",
					border_style="grey50",
					padding=(0, 1),
				),
				output_type=OutputType.DATA,
			)
		else:
			formatter.write(f"\n{display_cmd_name} options:\n")
			for line in lines:
				formatter.write(f"  {line}\n")

	if use_rich:
		rich_format_help(obj, ctx, formatter)
	else:
		formatter.write("\n" + "-" * 100 + "\n\n")
		super(type(obj), obj).format_help(ctx, formatter)


class OPSICLICommand(click.Command):
	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		_format_help(self, ctx, formatter)


class OPSICLIGroup(click.Group):
	def add_command(self, cmd: click.Command, name: Optional[str] = None) -> None:
		if isinstance(cmd, click.Group) and not isinstance(cmd, OPSICLIGroup):
			cmd.__class__ = OPSICLIGroup
		elif not isinstance(cmd, OPSICLICommand):
			cmd.__class__ = OPSICLICommand
		super().add_command(cmd, name)

	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		_format_help(self, ctx, formatter)
