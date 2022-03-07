"""
opsi-cli Basic command line interface for opsi
"""

import sys
import click
from opsicli.config import config

__version__ = "0.1.0"

PLUGIN_EXTENSION = "opsicliplug"


def prepare_cli_paths() -> None:
	if not config.plugin_dir.exists():
		config.plugin_dir.mkdir(parents=True)
		print("making", config.plugin_dir)
	if not config.lib_dir.exists():
		config.lib_dir.mkdir(parents=True)
		print("making", config.lib_dir)
	if str(config.lib_dir) not in sys.path:
		sys.path.append(str(config.lib_dir))
	print("path:", sys.path)


def prepare_context(ctx: click.Context) -> None:
	if ctx.obj is None:
		ctx.obj = {}
	if "plugins" not in ctx.obj:
		ctx.obj["plugins"] = {}
