# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli Basic command line interface for opsi
"""

import sys

from opsicli.config import config

__version__ = "4.3.15.0"


def prepare_cli_paths() -> None:
	if config.plugin_user_dir and not config.plugin_user_dir.exists():
		config.plugin_user_dir.mkdir(parents=True)

	if config.python_lib_dir and not config.python_lib_dir.exists():
		config.python_lib_dir.mkdir(parents=True)

	# Adding plugin dir
	if str(config.plugin_user_dir) not in sys.path:
		sys.path.append(str(config.plugin_user_dir))
