# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi
"""

import sys
from rich.console import Console
from opsicli.config import config

__version__ = "0.1.0"


def get_console():
	return Console(color_system="auto" if config.color else None)


def prepare_cli_paths() -> None:
	for plugin_dir in config.plugin_dirs:
		if not plugin_dir.exists():
			plugin_dir.mkdir(parents=True)
			# print("making", plugin_dir)
	if not config.lib_dir.exists():
		config.lib_dir.mkdir(parents=True)
		# print("making", lib_dir)
	if str(config.lib_dir) not in sys.path:
		sys.path.append(str(config.lib_dir))
	# print("path:", sys.path)
