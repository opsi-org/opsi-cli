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

from opsicli.config import config
from opsicli.io import OutputType, console_print, list_attributes


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
	setattr(func, "dry_run_capable", True)
	dry_run_note = "\n\nThis command supports --dry-run: actions will be simulated and not performed."
	func.__doc__ = (func.__doc__ or "") + dry_run_note

	@wraps(func)
	def wrapper(*args: Any, **kwargs: Any) -> Any:
		if config.dry_run:
			console_print("WARNING: Operating in dry-run mode - no actions will be performed.\n", output_type=OutputType.WARNING_MESSAGE)
		return func(*args, **kwargs)

	return wrapper
