# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli Basic command line interface for opsi
"""

import sys

from opsicommon.logging import get_logger

from opsicli.config import config

__version__ = "4.3.41.11"
logger = get_logger("opsi-cli")


def prepare_cli_paths() -> None:
	if config.plugin_user_dir and not config.plugin_user_dir.exists():
		try:
			config.plugin_user_dir.mkdir(parents=True)
		except PermissionError:
			logger.warning("Could not create plugin user directory '%s'. Please check the permissions.", config.plugin_user_dir)

	if config.python_lib_dir and not config.python_lib_dir.exists():
		try:
			config.python_lib_dir.mkdir(parents=True)
		except PermissionError:
			logger.warning("Could not create python lib directory '%s'. Please check the permissions.", config.python_lib_dir)
	# Adding plugin dir
	if config.plugin_user_dir and config.plugin_user_dir.exists() and str(config.plugin_user_dir) not in sys.path:
		sys.path.append(str(config.plugin_user_dir))
