# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli Basic command line interface for opsi

decorators
"""

import importlib
from functools import wraps
from typing import Any, Callable

import rich_click as click
from opsicommon.logging import get_logger

from opsicli.config import config
from opsicli.io import OutputType, console_print, list_attributes

logger = get_logger("opsicli")


def handle_list_attributes(func: Callable) -> Callable:
	@wraps(func)
	def wrapper_func(ctx: click.Context, *args: Any, **kwargs: Any) -> Any:
		if config.list_attributes and isinstance(ctx.command, click.Group) and ctx.invoked_subcommand is not None:
			invoked_subcommand = ctx.command.get_command(ctx, ctx.invoked_subcommand)
			if invoked_subcommand and not isinstance(invoked_subcommand, click.Group):
				command_sequence = "_".join(ctx.command_path.split(" ")[1:]) + f"_{ctx.invoked_subcommand}"
				plugin_name = command_sequence.split("_")[0]
				module = importlib.import_module(f"plugins.{plugin_name}.data.metadata")
				command_metadata = getattr(module, "command_metadata")
				metadata = command_metadata.get(command_sequence)

				if metadata:
					list_attributes(metadata)
					ctx.exit()
		return func(ctx, *args, **kwargs)

	return wrapper_func


def dry_run_handling(dry_run_capable: bool = False) -> Callable:
	"""
	Decorator for Click commands and groups to handle --dry-run.

	If dry_run_capable is False (default), using --dry-run will abort with an error.
	If dry_run_capable is True, the command allows --dry-run, adds a help note indicating dry-run support, and shows a warning if --dry-run is used.
	"""

	def abort_if_not_dry_run_capable(ctx: click.Context, command_name: str) -> None:
		console_print(
			f"ERROR: The command '{command_name}' does not support --dry-run. Aborting.",
			output_type=OutputType.ERROR_MESSAGE,
		)
		logger.error("The command '%s' does not support --dry-run. Aborting.", command_name)
		ctx.exit(1)

	def decorator(func: Callable) -> Callable:
		setattr(func, "dry_run_capable", dry_run_capable)

		# Append a note to the function's docstring about dry-run support
		if dry_run_capable:
			dry_run_note = "\n\nThis command supports --dry-run: actions will be simulated and not performed."
			func.__doc__ = (func.__doc__ or "") + dry_run_note

		@wraps(func)
		def wrapper(ctx: click.Context, *args: Any, **kwargs: Any) -> Any:
			if config.dry_run:
				is_group = hasattr(ctx.command, "get_command")
				subcmd = getattr(ctx, "invoked_subcommand", None)
				if is_group and subcmd:
					get_command = getattr(ctx.command, "get_command", None)
					subcommand_obj = get_command(ctx, subcmd) if get_command else None
					callback = getattr(subcommand_obj, "callback", None)
					if not getattr(callback, "dry_run_capable", False):
						abort_if_not_dry_run_capable(ctx, subcmd)
					return func(ctx, *args, **kwargs)
				if dry_run_capable:
					warning_message = "WARNING: Operating in dry-run mode - no actions will be performed."
					console_print(f"{warning_message}\n", output_type=OutputType.WARNING_MESSAGE)
					logger.warning(warning_message)
				else:
					command_name = ctx.command.name or ctx.command_path
					abort_if_not_dry_run_capable(ctx, command_name)
			return func(ctx, *args, **kwargs)

		return wrapper

	return decorator
