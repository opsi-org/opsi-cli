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
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli.config import config
from opsicli.io import Attribute, Metadata, get_console, prompt, write_output
from opsicli.plugin import (
	PLUGIN_EXTENSION,
	OPSICLIPlugin,
	install_plugin,
	plugin_manager,
	prepare_plugin,
	replace_data,
)

__version__ = "0.1.2"

logger = get_logger("opsicli")


@click.group(name="plugin", short_help="Manage opsi-cli plugins")
@click.version_option(__version__, message="opsi plugin, version %(version)s")
def cli() -> None:  # pylint: disable=unused-argument
	"""
	opsi-cli plugin command.
	This command is used to add, remove, list or export plugins to opsi-cli.
	"""
	logger.trace("plugin command")


@cli.command(short_help=f"Add new plugin (python package or .{PLUGIN_EXTENSION})")
@click.argument("paths", type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path), nargs=-1)
@click.option(
	"--system/--user",
	help=("Install system wide or for current user."),
	default=False,
	show_default=True,
)
def add(paths: list[Path], system: bool) -> None:
	"""
	opsi-cli plugin add subcommand.
	Specify a path to a python package directory or an opsi-cli plugin file
	to install it as plugin for opsi-cli
	"""
	for path in paths:
		with tempfile.TemporaryDirectory() as tmpdir:
			tmpdir_path = Path(tmpdir)
			(tmpdir_path / "lib").mkdir(parents=True, exist_ok=True)
			plugin_id = prepare_plugin(path, tmpdir_path)
			try:
				path = install_plugin(tmpdir_path, plugin_id, system)
			except PermissionError as p_error:
				logger.error(p_error, exc_info=True)
				continue
		get_console().print(f"Plugin {plugin_id!r} installed into '{path}'.")


@cli.command(short_help=f"Export plugin as .{PLUGIN_EXTENSION}")
@click.argument("plugin_id", type=str)
@click.argument("destination_dir", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), default=Path("."))
@click.option("--src", help="Extract as directory instead of .opsicliplug", is_flag=True, show_default=True, default=False)
def export(plugin_id: str, destination_dir: Path, src: bool) -> None:
	"""
	opsi-cli plugin export subcommand.
	This subcommand is used to export an installed opsi-cli plugin.
	It is packaged as an opsi-cli plugin file which can be added to another
	instance of opsi-cli via "plugin add". Also see "plugin list".
	"""
	destination_dir.mkdir(parents=True, exist_ok=True)
	path = plugin_manager.get_plugin_dir(plugin_id)
	logger.debug("Getting plugin from path %s", path)

	if src:
		destination = destination_dir / plugin_id
		if (destination).exists():
			raise FileExistsError(f"Directory {destination} exists! Remove it before exporting {plugin_id} in 'src' mode.")
		logger.notice("Exporting plugin %r to %r", plugin_id, destination)
		shutil.copytree(path, destination)
		return

	destination = destination_dir / f"{plugin_id}.{PLUGIN_EXTENSION}"
	logger.notice("Exporting plugin %r to %r", plugin_id, destination)
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


@cli.command(short_help=f"Extract source from .{PLUGIN_EXTENSION}")
@click.argument("archive", type=click.Path(file_okay=True, dir_okay=False, path_type=Path))
@click.argument("destination_dir", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), default=Path("."))
def extract(archive: Path, destination_dir: Path) -> None:
	"""
	opsi-cli plugin extract subcommand.
	This subcommand is used to extract an archive to its source plugin state.
	The operation is performed without importing the plugin.
	The running opsi-cli instance is unaffected.
	"""
	plugin_id = archive.stem
	if (destination_dir / plugin_id).exists():
		raise FileExistsError(f"Directory {destination_dir / plugin_id} exists! Remove it before extracting {archive} to {destination_dir}")
	logger.notice("Extracting plugin archive %s to path %s", archive, destination_dir)
	with zipfile.ZipFile(archive, "r", zipfile.ZIP_DEFLATED) as zfile:
		zfile.extractall(path=str(destination_dir))
	get_console().print(f"Plugin archive {archive!s} extracted to '{destination_dir!s}'")


@cli.command(short_help=f"Compress plugin source directory to .{PLUGIN_EXTENSION} archive")
@click.argument("source_dir", type=click.Path(file_okay=False, dir_okay=True, path_type=Path))
@click.argument("destination_dir", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), default=Path("."))
def compress(source_dir: Path, destination_dir: Path) -> None:
	"""
	opsi-cli plugin compress subcommand.
	This subcommand is used to compress a plugin source directory to an archive.
	The operation is performed without importing the plugin.
	The running opsi-cli instance is unaffected.
	"""
	plugin_id = source_dir.stem
	archive = destination_dir / f"{plugin_id}.{PLUGIN_EXTENSION}"
	if (archive).exists():
		raise FileExistsError(f"Archive {archive} exists! Remove it before compressing {source_dir} to {destination_dir}")
	logger.notice("Compressing plugin directory %s to archive %s", source_dir, archive)
	with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zfile:
		for root, _, files in os.walk(source_dir):
			root_path = Path(root)
			if root_path.name in ("__pycache__",):
				continue
			base = root_path.relative_to(source_dir)
			for single_file in files:
				logger.debug("Adding file '%s'", root_path / single_file)
				zfile.write(str(root_path / single_file), arcname=str(Path(plugin_id) / base / single_file))
	get_console().print(f"Plugin source {source_dir!s} compressed to '{archive!s}'")


@cli.command(name="list", short_help="List imported plugins")
def list_() -> None:
	"""
	opsi-cli plugin list subcommand.
	This subcommand lists all installed opsi-cli plugins.
	"""

	metadata = Metadata(
		attributes=[
			Attribute(id="id", description="Plugin ID", identifier=True),
			Attribute(id="name", description="Name of the Plugin"),
			Attribute(id="description", description="Plugin description"),
			Attribute(id="version", description="Version of the plugin"),
			Attribute(id="path", description="Location of the plugin"),
		]
	)
	data = []
	for plugin_id in sorted(plugin_manager.plugins):
		plugin = plugin_manager.load_plugin(plugin_id)
		data.append(
			{"id": plugin_id, "name": plugin.name, "description": plugin.description, "version": plugin.version, "path": plugin.path}
		)
	write_output(data, metadata)


@cli.command(short_help="Remove a plugin")
@click.argument("plugin_id", type=str)
def remove(plugin_id: str) -> None:
	"""
	opsi-cli plugin remove subcommand.
	This subcommand removes an installed opsi-cli plugin. See "[bold]plugin list[/bold]".
	"""
	plugin_object = plugin_manager.load_plugin(plugin_id)
	if "protected" in plugin_object.flags:
		raise PermissionError(f"Plugin {plugin_id} has flag 'protected', cannot remove!")
	path = plugin_object.path
	found = False
	for plugin_dir in (config.plugin_user_dir, config.plugin_system_dir):
		if plugin_dir in path.parents:
			found = True
			break
	if not found:
		raise ValueError(f"Attempt to remove plugin from invalid path {path!r} - Stopping.")
	logger.notice("Removing plugin %s", plugin_id)
	del plugin_object  # Necessary? windows?
	logger.debug("Deleting plugin path %s", path)
	shutil.rmtree(path)
	if (config.python_lib_dir / plugin_id).exists():
		logger.debug("Deleting plugin dependencies %s", config.python_lib_dir / plugin_id)
		shutil.rmtree(config.python_lib_dir / plugin_id)
	get_console().print(f"Plugin {plugin_id!r} removed")


@cli.command(short_help="Create a new plugin")
@click.argument("name", type=str, required=False)
@click.option("--version", help="Version number of the new plugin", type=str)
@click.option("--description", help="Version number of the new plugin", type=str)
@click.option(
	"--path", help="Path to put plugin template", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), default=Path(".")
)
def new(name: str, version: str, description: str, path: Path) -> None:
	"""
	opsi-cli plugin new subcommand.
	This subcommand creates a new plugin.
	"""
	if not name:
		if not config.interactive:
			raise ValueError("No name specified")
		name = str(prompt("Please enter a name for the new plugin"))
		if not name:
			raise ValueError("Plugin name must not be empty")
	if not version:
		if not config.interactive:
			raise ValueError("No version specified")
		version = str(prompt("Please enter version number", default="0.1.0"))
	if description is None:
		if not config.interactive:
			description = ""
		else:
			description = str(prompt("Please enter description", default="")).replace('"', '\\"')
	plugin_id = name.lower()
	logger.notice("Creating new plugin '%s'", plugin_id)
	logger.debug("name='%s', version='%s', description='%s'", name, version, description)
	result_path = path / plugin_id
	if result_path.exists():
		raise FileExistsError(f"Path {result_path} already exists. Aborting.")
	(result_path / "python").mkdir(parents=True)
	(result_path / "data").mkdir()

	template_file_path = plugin_manager.get_plugin_dir("plugin") / "data" / "template.py"  # Configurable?
	if not template_file_path.exists():
		raise FileNotFoundError("No template file for new plugins found!")
	replacements = {
		"{{VERSION}}": version,
		"{{NAME}}": name,
		"{{ID}}": plugin_id,
		"{{DESCRIPTION}}": description,
	}

	with open(result_path / "python" / "__init__.py", "w", encoding="utf-8") as initfile:
		with open(template_file_path, "r", encoding="utf-8") as templatefile:
			for line in templatefile.readlines():
				initfile.write(replace_data(line, replacements))
	get_console().print(
		f"Plugin {plugin_id!r} created at path {path}.\n"
		f"Add code to {path / 'python'} and optional data to {path / 'data'}\n"
		f"Use 'opsi-cli plugin add {result_path}' to register the command at the current opsi-cli instance and to apply changes."
	)


class PluginPlugin(OPSICLIPlugin):
	name: str = "Plugin"
	description: str = "Manage opsi-cli plugins"
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
