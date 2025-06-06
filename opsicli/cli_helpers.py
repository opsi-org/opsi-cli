from typing import Optional

import rich_click as click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree
from rich_click.rich_click import rich_format_help


def _get_command_hierarchy(ctx: click.Context) -> Panel:
	chain = []
	current: Optional[click.Context] = ctx
	while current:
		chain.append(current)
		current = current.parent
	chain = list(reversed(chain))

	max_cmd_len = max(len(c.command.name or "") for c in chain)

	root_ctx = chain[0]
	root_cmd = root_ctx.command
	root_name = "opsi-cli"
	root_help = (getattr(root_cmd, "short_help", "") or getattr(root_cmd, "help", "")).strip().splitlines()[0]
	root_label = Text.assemble(
		(root_name.ljust(max_cmd_len), "bold cyan"),
		(f"  {root_help}" if root_help else ""),
	)
	tree = Tree(root_label)
	parent = tree
	for c in chain[1:]:
		cmd = c.command
		cmd_name = (cmd.name or "").ljust(max_cmd_len)
		help_text = (getattr(cmd, "short_help", "") or getattr(cmd, "help", "")).strip().splitlines()[0]
		label = Text.assemble(
			(cmd_name, "bold cyan"),
			(f"  {help_text}" if help_text else ""),
		)
		parent = parent.add(label)
	return Panel(tree, title="Command Path", padding=(0, 1))


class OpsiCLICommand(click.Command):
	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		rich_format_help(self, ctx, formatter)
		console = Console()
		console.print(_get_command_hierarchy(ctx))


class OpsiCLIGroup(click.Group):
	def add_command(self, cmd: click.Command, name: Optional[str] = None) -> None:
		if isinstance(cmd, click.Group) and not isinstance(cmd, OpsiCLIGroup):
			cmd.__class__ = OpsiCLIGroup
		elif isinstance(cmd, click.Command) and not isinstance(cmd, OpsiCLICommand):
			cmd.__class__ = OpsiCLICommand
		super().add_command(cmd, name)

	def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
		rich_format_help(self, ctx, formatter)
		console = Console()
		console.print(_get_command_hierarchy(ctx))
