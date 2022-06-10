# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi
"""

import sys

from opsicli.config import config

__version__ = "0.1.1"


def prepare_cli_paths() -> None:
	if config.plugin_user_dir and not config.plugin_user_dir.exists():
		config.plugin_user_dir.mkdir(parents=True)

	if config.python_lib_dir and not config.python_lib_dir.exists():
		config.python_lib_dir.mkdir(parents=True)

	if str(config.python_lib_dir) not in sys.path:
		sys.path.append(str(config.python_lib_dir))
