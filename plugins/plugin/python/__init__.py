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
from opsicli.plugin import OPSICLIPlugin, PLUGIN_EXTENSION, plugin_manager, install_plugin, prepare_plugin

__version__ = "0.1.0"


@click.group(name="plugin", short_help="Manage opsi-cli plugins")
@click.version_option(__version__, message="opsi plugin, version %(version)s")
def cli() -> None:  # pylint: disable=unused-argument
	"""
	opsi-cli plugin command.
	This command is used to add, remove, list or export plugins to opsi-cli.
	"""
	logger.trace("plugin command")


@cli.command(short_help=f"Add new plugin (python package or .{PLUGIN_EXTENSION})")
@click.argument("path", type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path))
def add(path: Path) -> None:
	"""
	opsi-cli plugin add subcommand.
	Specify a path to a python package directory or an opsi-cli plugin file
	to install it as plugin for opsi-cli
	"""
	with tempfile.TemporaryDirectory() as tmpdir:
		tmpdir_path = Path(tmpdir)
		(tmpdir_path / "lib").mkdir(parents=True, exist_ok=True)
		name = prepare_plugin(path, tmpdir_path)
		install_plugin(tmpdir_path, name)
	get_console().print(f"Plugin {name!r} installed")


@cli.command(short_help=f"Export plugin as .{PLUGIN_EXTENSION}")
@click.argument("plugin_id", type=str)
@click.argument("destination_dir", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), default=Path("."))
def export(plugin_id: str, destination_dir: Path) -> None:
	"""
	opsi-cli plugin export subcommand.
	This subcommand is used to export an installed opsi-cli plugin.
	It is packaged as an opsi-cli plugin file which can be added to another
	instance of opsi-cli via "plugin add". Also see "plugin list".
	"""
	destination_dir.mkdir(parents=True, exist_ok=True)
	destination = destination_dir / f"{plugin_id}.{PLUGIN_EXTENSION}"
	logger.notice("Exporting plugin %r to %r", plugin_id, destination)
	path = plugin_manager.get_plugin(plugin_id).path

	logger.debug("Compressing plugin path %s", path)

	with zipfile.ZipFile(f"{plugin_id}.{PLUGIN_EXTENSION}", "w", zipfile.ZIP_DEFLATED) as zfile:
		for root, _, files in os.walk(path):
			root_path = Path(root)
			if root_path.name in ("__pycache__",):
				continue
			base = root_path.relative_to(path)
			for single_file in files:
				logger.debug("Adding file '%s'", root_path / single_file)
				zfile.write(str(root_path / single_file), arcname=str(Path(plugin_id) / base / single_file))
	get_console().print(f"Plugin {plugin_id!r} exported to '{destination!s}'")


@cli.command(name="list", short_help="List imported plugins")
def list_() -> None:
	"""
	opsi-cli plugin list subcommand.
	This subcommand lists all installed opsi-cli plugins.
	"""
	table = Table()

	table.add_column("ID", style="cyan", no_wrap=True)
	table.add_column("Name")
	table.add_column("Description")
	table.add_column("Version")

	for plugin in sorted(plugin_manager.plugins, key=lambda plugin: plugin.id):
		table.add_row(plugin.id, plugin.name, plugin.description, plugin.version)

	get_console().print(table)


@cli.command(short_help="Remove a plugin")
@click.argument("plugin_id", type=str)
def remove(plugin_id: str) -> None:
	"""
	opsi-cli plugin remove subcommand.
	This subcommand removes an installed opsi-cli plugin. See "plugin list".
	"""
	path = plugin_manager.get_plugin(plugin_id).path
	found = False
	for plugin_dir in config.plugin_dirs:
		if plugin_dir in path.parents:
			found = True
			break
	if not found:
		raise ValueError(f"Attempt to remove plugin from invalid path {path!r} - Stopping.")
	logger.notice("Removing plugin %s", plugin_id)
	logger.debug("Deleting %s", path)
	shutil.rmtree(path)
	get_console().print(f"Plugin {plugin_id!r} removed")


class ConfigPlugin(OPSICLIPlugin):
	id: str = "plugin"  # pylint: disable=invalid-name
	name: str = "Plugin"
	description: str = "Manage opsi-cli plugins"
	version: str = __version__
	cli = cli
