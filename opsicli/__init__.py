# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi
"""

import sys
import pathlib
import click
from opsicli.config import config

__version__ = "0.1.0"

PLUGIN_EXTENSION = "opsicliplug"


def prepare_cli_paths() -> None:
	plugin_dir = pathlib.Path(config.plugin_dir)
	lib_dir = pathlib.Path(config.lib_dir)
	if not plugin_dir.exists():
		plugin_dir.mkdir(parents=True)
		print("making", plugin_dir)
	if not lib_dir.exists():
		lib_dir.mkdir(parents=True)
		print("making", lib_dir)
	if str(lib_dir) not in sys.path:
		sys.path.append(str(lib_dir))
	##print("path:", sys.path)


def prepare_context(ctx: click.Context) -> None:
	if ctx.obj is None:
		ctx.obj = {}
	if "plugins" not in ctx.obj:
		ctx.obj["plugins"] = {}
