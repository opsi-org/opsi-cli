import os
import re
from typing import Any, Optional

from rich.panel import Panel
from rich.text import Text

from opsicli.config import config
from opsicli.io import OutputType, console_print, get_console

COMPLETION_MODE = "_OPSI_CLI_COMPLETE" in os.environ or "_OPSI_CLI_EXE_COMPLETE" in os.environ

if COMPLETION_MODE:
	import click
else:
	import rich_click as click  # type: ignore[no-redef]
	import rich_click.rich_click as rich_click
	from rich_click.rich_click import rich_format_help


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

		rich_click.get_rich_usage = _custom_get_rich_usage
		rich_format_help(obj, ctx, formatter)

	else:
		formatter.write("\n" + "-" * 100 + "\n\n")
		formatter.write(f"\n{custom_usage}\n")
		type(obj).format_usage = lambda self, ctx, formatter: None
		super(type(obj), obj).format_help(ctx, formatter)


def _get_usage(ctx: click.Context) -> str:
	orig_usage = super(type(ctx.command), ctx.command).get_usage(ctx)

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


class OPSICLICommand(click.Command):
	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		_format_help(self, ctx, formatter)

	def get_usage(self, ctx: click.Context) -> str:
		return _get_usage(ctx)


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
