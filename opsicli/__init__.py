# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi
"""

import sys

from opsicli.config import config

__version__ = "0.1.0"


def prepare_cli_paths() -> None:
	for plugin_dir in config.plugin_dirs:
		if not plugin_dir.exists():
			plugin_dir.mkdir(parents=True)
			# print("making", plugin_dir)
	if not config.python_lib_dir.exists():
		config.python_lib_dir.mkdir(parents=True)
		# print("making", python_lib_dir)
	if str(config.python_lib_dir) not in sys.path:
		sys.path.append(str(config.python_lib_dir))
	# print("path:", sys.path)
