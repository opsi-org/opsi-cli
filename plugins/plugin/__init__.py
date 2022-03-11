"""
opsi-cli basic command line interface for opsi

plugin subcommand
"""


import os
import shutil
import tempfile
import zipfile
from typing import Any, Dict
from pathlib import Path

from rich.table import Table
import rich_click as click  # type: ignore[import]

from opsicommon.logging import logger  # type: ignore[import]

from opsicli import get_console
from opsicli.config import config
from opsicli.plugin import PLUGIN_EXTENSION, plugin_manager, install_plugin, prepare_plugin

__version__ = "0.1.0"


def get_plugin_info() -> Dict[str, Any]:
	return {"name": "plugin", "description": "Manage opsi-cli plugins", "version": __version__}


@click.group(name="plugin", short_help="Manage opsi-cli plugins")
@click.version_option(__version__, message="opsi plugin, version %(version)s")
def cli() -> None:  # pylint: disable=unused-argument
	"""
	opsi-cli plugin command.
	This command is used to add, remove, list or export plugins to opsi-cli.
	"""
	logger.trace("plugin command")


@cli.command(short_help=f"Add new plugin (python package or .{PLUGIN_EXTENSION})")
@click.argument("path", type=click.Path(exists=True))
def add(path: str) -> None:
	"""
	opsi-cli plugin add subcommand.
	Specify a path to a python package directory or an opsi-cli plugin file
	to install it as plugin for opsi-cli
	"""
	with tempfile.TemporaryDirectory() as tmpdir:
		tmpdir_path = Path(tmpdir)
		(tmpdir_path / "lib").mkdir(parents=True, exist_ok=True)
		name = prepare_plugin(Path(path), tmpdir_path)
		install_plugin(tmpdir_path, name)
	get_console().print(f"Plugin {name!r} installed")


@cli.command(short_help=f"Export plugin as .{PLUGIN_EXTENSION}")
@click.argument("name", type=str)
def export(name: str) -> None:
	"""
	opsi-cli plugin export subcommand.
	This subcommand is used to export an installed opsi-cli plugin.
	It is packaged as an opsi-cli plugin file which can be added to another
	instance of opsi-cli via "plugin add". Also see "plugin list".
	"""
	logger.notice("Exporting command %r to %r", name, f"{name}.{PLUGIN_EXTENSION}")
	path = plugin_manager.get_plugin_path(name)
	logger.debug("Compressing plugin path %s", path)

	with zipfile.ZipFile(f"{name}.{PLUGIN_EXTENSION}", "w", zipfile.ZIP_DEFLATED) as zfile:
		for root, _, files in os.walk(path):
			root_path = Path(root)
			base = root_path.relative_to(path)
			for single_file in files:
				zfile.write(str(root_path / single_file), arcname=str(Path(name) / base / single_file))
	get_console().print(f"Plugin {name!r} exported")


@cli.command(name="list", short_help="List imported plugins")
def list_command() -> None:
	"""
	opsi-cli plugin list subcommand.
	This subcommand lists all installed opsi-cli plugins.
	"""
	table = Table()

	table.add_column("Name", style="cyan", no_wrap=True)
	table.add_column("Description")
	table.add_column("Version")

	for plugin_name in sorted(plugin_manager.plugin_modules.keys()):
		info = plugin_manager.plugin_modules[plugin_name].get_plugin_info()
		table.add_row(info["name"], info["description"], info["version"])

	get_console().print(table)


@cli.command(short_help="Remove a plugin")
@click.argument("name", type=str)
def remove(name: str) -> None:
	"""
	opsi-cli plugin remove subcommand.
	This subcommand removes an installed opsi-cli plugin. See "plugin list".
	"""
	path = plugin_manager.get_plugin_path(name)
	found = False
	for plugin_dir in config.plugin_dirs:
		if plugin_dir in path.parents:
			found = True
			break
	if not found:
		raise ValueError(f"Attempt to remove plugin from invalid path {path!r} - Stopping.")
	logger.notice("Removing plugin %s", name)
	logger.debug("Deleting %s", path)
	shutil.rmtree(path)
	get_console().print(f"Plugin {name!r} removed")
