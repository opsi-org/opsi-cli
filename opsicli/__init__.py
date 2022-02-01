"""
opsi-cli Basic command line interface for opsi
"""

import os
import sys
import click
from opsicli.config import config

__version__ = "0.1.0"


def prepare_cli_paths() -> None:
	if not config.plugin_dir.exists():
		os.makedirs(config.plugin_dir)
	if not config.lib_dir.exists():
		os.makedirs(config.lib_dir)
	if config.lib_dir not in sys.path:
		sys.path.append(str(config.lib_dir))


def prepare_context(ctx: click.Context) -> None:
	if ctx.obj is None:
		ctx.obj = {}
	if "plugins" not in ctx.obj:
		ctx.obj["plugins"] = {}
