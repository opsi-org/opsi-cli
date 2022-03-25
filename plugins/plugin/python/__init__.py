"""
opsi-cli basic command line interface for opsi

plugin subcommand
"""


import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import rich_click as click  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.config import config
from opsicli.io import get_console, write_output
from opsicli.plugin import (
	PLUGIN_EXTENSION,
	OPSICLIPlugin,
	install_plugin,
	plugin_manager,
	prepare_plugin,
)

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

	with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zfile:
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

	metadata = {
		"attributes": [
			{"id": "id", "description": "Plugin ID", "identifier": True},
			{"id": "name", "description": "Name of the Plugin"},
			{"id": "description", "description": "Plugin description"},
			{"id": "version", "description": "Version of the plugin"},
		]
	}
	data = []
	for plugin in sorted(plugin_manager.plugins, key=lambda plugin: plugin.id):
		data.append({"id": plugin.id, "name": plugin.name, "description": plugin.description, "version": plugin.version})

	write_output(data, metadata)


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
	plugin_manager.unload_plugin(plugin_id)
	logger.debug("Deleting %s", path)
	shutil.rmtree(path)
	get_console().print(f"Plugin {plugin_id!r} removed")


@cli.command(short_help="Create a new plugin")
@click.option("--name", help="Name of the new plugin (default: same as id)", type=str, prompt=True)
@click.option("--version", help="Version number of the new plugin", type=str, prompt=True, default="0.1.0")
@click.option("--description", help="Version number of the new plugin", type=str, prompt=True, default="")
@click.option(
	"--path", help="Path to put plugin template", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), default=Path(".")
)
def new(name: str, version: str, description: str, path: Path) -> None:
	"""
	opsi-cli plugin new subcommand.
	This subcommand creates a new plugin.
	"""
	assert name, "Plugin name must not be empty"
	plugin_id = name.lower()
	logger.notice("Creating new plugin '%s'", plugin_id)
	logger.debug("name='%s', version='%s', description='%s'", name, version, description)
	result_path = path / plugin_id
	assert not result_path.exists(), f"Path {result_path} already exists. Aborting."
	result_path.mkdir()

	template_file_path = None
	for plugin_dir in config.plugin_dirs:
		if (plugin_dir / "plugin" / "data" / "template.py").exists():
			template_file_path = plugin_dir / "plugin" / "data" / "template.py"  # TODO: Configurable?
	assert template_file_path, "No template file for new plugins found!"

	with open(result_path / "__init__.py", "w", encoding="utf-8") as initfile:
		with open(template_file_path, "r", encoding="utf-8") as templatefile:
			for line in templatefile.readlines():
				# TODO: replace placeholders in template
				initfile.write(line)
	get_console().print(f"Plugin {plugin_id!r} created at path {path}. Add it to this instance by using 'opsi-cli add {path}'")


class PluginPlugin(OPSICLIPlugin):
	id: str = "plugin"  # pylint: disable=invalid-name
	name: str = "Plugin"
	description: str = "Manage opsi-cli plugins"
	version: str = __version__
	cli = cli
