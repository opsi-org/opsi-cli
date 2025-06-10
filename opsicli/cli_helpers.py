from typing import Optional

import rich_click as click
from rich.padding import Padding
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree
from rich_click.rich_click import rich_format_help

from opsicli.config import config
from opsicli.io import OutputType, console_print


def _get_command_hierarchy(ctx: click.Context) -> Tree:
	"""
	Builds a tree showing the path from the root command to the current subcommand.
	Each level displays the command name and its short help text.
	"""
	chain = []
	current: Optional[click.Context] = ctx
	while current:
		chain.append(current)
		current = current.parent
	chain.reverse()

	max_cmd_len = max(len(c.command.name or "") for c in chain)

	def get_help(cmd: click.Command) -> str:
		help_text = getattr(cmd, "short_help", "") or getattr(cmd, "help", "")
		return help_text.strip().splitlines()[0] if help_text else ""

	root_cmd = chain[0].command
	root_label = Text.assemble(
		("opsi-cli".ljust(max_cmd_len), "bold cyan"),
		(f"  {get_help(root_cmd)}" if get_help(root_cmd) else ""),
	)
	tree = Tree(root_label)
	parent = tree
	for c in chain[1:]:
		cmd = c.command
		label = Text.assemble(
			((cmd.name or "").ljust(max_cmd_len), "bold cyan"),
			(f"  {get_help(cmd)}" if get_help(cmd) else ""),
		)
		parent = parent.add(label)
	return tree


def _format_help(obj: click.Command, ctx: click.Context, formatter: click.HelpFormatter) -> None:
	config.read_config_files()
	use_rich = config.color and "rich_format_help" in globals()
	if use_rich:
		rich_format_help(obj, ctx, formatter)
		console_print(
			Panel(
				_get_command_hierarchy(ctx),
				title="Command Hierarchy",
				title_align="left",
				padding=(0, 1),
				border_style="grey37",
			),
			output_type=OutputType.DATA,
		)
	else:
		formatter = click.HelpFormatter()
		if isinstance(obj, OPSICLIGroup):
			super(OPSICLIGroup, obj).format_help(ctx, formatter)
		elif isinstance(obj, OPSICLICommand):
			super(OPSICLICommand, obj).format_help(ctx, formatter)
		elif isinstance(obj, click.Group):
			click.Group.format_help(obj, ctx, formatter)
		elif isinstance(obj, click.Command):
			click.Command.format_help(obj, ctx, formatter)
		else:
			raise TypeError(f"Unsupported command type: {type(obj)}")
		help_text = formatter.getvalue()
		console_print(help_text, output_type=OutputType.DATA)
		console_print("Command Hierarchy:", output_type=OutputType.DATA)
		console_print(Padding(_get_command_hierarchy(ctx), (0, 2)), output_type=OutputType.DATA)


class OPSICLICommand(click.Command):
	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		_format_help(self, ctx, formatter)


class OPSICLIGroup(click.Group):
	def add_command(self, cmd: click.Command, name: Optional[str] = None) -> None:
		if isinstance(cmd, click.Group) and not isinstance(cmd, OPSICLIGroup):
			cmd.__class__ = OPSICLIGroup
		elif isinstance(cmd, click.Command) and not isinstance(cmd, OPSICLICommand):
			cmd.__class__ = OPSICLICommand
		super().add_command(cmd, name)

	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		_format_help(self, ctx, formatter)
