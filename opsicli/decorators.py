# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli Basic command line interface for opsi

decorators
"""

from functools import wraps

from opsicommon.logging import get_logger

logger = get_logger("opsicli")


def dry_run_capable(func):
	setattr(func, "is_dry_run_handled", True)

	@wraps(func)
	def wrapper(*args, **kwargs):
		return func(*args, **kwargs)

	return wrapper
