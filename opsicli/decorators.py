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


def dry_run_capable(func: Callable) -> Callable:
	"""
	This decorator:
	- Marks the function as capable of dry-run execution.
	- Appends a note to the command's help message indicating dry-run support.
	- Displays a warning to the user if --dry-run is enabled.
	"""
	setattr(func, "dry_run_capable", True)

	# Append a note to the function's docstring about dry-run support
	dry_run_note = "\n\nThis command supports --dry-run: actions will be simulated and not performed."
	func.__doc__ = (func.__doc__ or "") + dry_run_note

	@wraps(func)
	def wrapper(*args: Any, **kwargs: Any) -> Any:
		if config.dry_run:
			warning_message = "WARNING: Operating in dry-run mode - no actions will be performed."
			console_print(f"{warning_message}\n", output_type=OutputType.WARNING_MESSAGE)
			logger.warning(warning_message)
		return func(*args, **kwargs)

	return wrapper


def dry_run_guard(func: Callable) -> Callable:
	"""
	Decorator for Click command groups.
	If --dry-run is set and the invoked subcommand is not dry-run-capable, abort with an error.
	"""

	@wraps(func)
	def wrapper(ctx: click.Context, *args: Any, **kwargs: Any) -> Any:
		if hasattr(ctx, "invoked_subcommand") and ctx.invoked_subcommand:
			get_command = getattr(ctx.command, "get_command", None)
			command = get_command(ctx, ctx.invoked_subcommand) if get_command else None
			callback = getattr(command, "callback", None)
			if config.dry_run and not getattr(callback, "dry_run_capable", False):
				console_print(
					f"ERROR: The command '{ctx.invoked_subcommand}' does not support --dry-run. Aborting.\n",
					output_type=OutputType.ERROR_MESSAGE,
				)
				logger.error(
					"The command '%s' does not support --dry-run. Aborting.",
					ctx.invoked_subcommand,
				)
				ctx.exit(1)
		return func(ctx, *args, **kwargs)

	return wrapper
