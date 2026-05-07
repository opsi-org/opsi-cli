# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli Basic command line interface for opsi

decorators
"""

from functools import wraps

import click
from opsi.logging import get_logger

logger = get_logger("opsicli")


def dry_run_capable(func):
	setattr(func, "is_dry_run_handled", True)
	# add dry-run capability to docstring
	dry_run_note = "\n\n* This command supports --dry-run: actions will be simulated and not performed."
	func.__doc__ = (func.__doc__ or "") + dry_run_note

	@wraps(func)
	def wrapper(*args, **kwargs):
		return func(*args, **kwargs)

	return wrapper


def mutually_exclusive(*options):
	def decorator(func):
		@wraps(func)
		def wrapper(*args, **kwargs):
			opt_list = [f"--{opt}" for opt in options if kwargs.get(opt)]
			if "--all" in opt_list and "--where" in opt_list:
				raise click.UsageError(f"The options {', '.join(opt_list)} are mutually exclusive.")
			return func(*args, **kwargs)

		return wrapper

	return decorator
