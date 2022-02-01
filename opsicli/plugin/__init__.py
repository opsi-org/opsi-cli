"""
opsi-cli Basic command line interface for opsi

plugin subcommand
"""

import importlib
import os
import shutil
import subprocess
import tempfile
import zipfile
from typing import Dict
from pathlib import Path
from packaging.version import parse
import click
from pipreqs import pipreqs

from opsicommon.logging import logger

from opsicli.config import get_python_path, config

__version__ = "0.1.0"


def get_plugin_name() -> str:
	return "plugin"


@click.group(name="plugin", short_help="Manage opsi CLI plugins")
@click.version_option(__version__, message="opsi plugin, version %(version)s")
@click.pass_context
def cli(ctx: click.Context) -> None:  # pylint: disable=unused-argument
	"""
	opsi plugin command.
	This command is used to add, remove, list or export plugins to opsi cli.
	"""
	logger.trace("plugin command")


@cli.command(short_help='Add new plugin (python package or .opsiplugin)')
@click.argument('path', type=click.Path(exists=True))
def add(path: str) -> None:
	"""
	opsi plugin add subcommand.
	Specify a path to a python package directory or .opsiplugin file to
	install it as plugin for opsi cli
	"""
	with tempfile.TemporaryDirectory() as tmpdir:
		tmpdir = Path(tmpdir)
		os.makedirs(tmpdir / "lib")
		name = prepare_plugin(Path(path), tmpdir)
		install_plugin(tmpdir, name)


# this creates the plugin command and libs in tmp
def prepare_plugin(path: str, tmpdir: str) -> str:
	logger.info("Inspecting plugin source %s", path)
	name = path.stem
	if (path / "__init__.py").exists():
		shutil.copytree(path, tmpdir / name)
	elif path.suffix == ".opsiplugin":
		with zipfile.ZipFile(path, "r") as zfile:
			zfile.extractall(tmpdir)
	else:
		raise ValueError(f"Invalid path given {path}")

	logger.info("Retrieving libraries for new plugin")
	install_dependencies(tmpdir / name, tmpdir / "lib")
	return name


# this copies the prepared plugin from tmp to LIB_DIR
def install_plugin(source_dir: str, name: str) -> None:
	logger.info("Installing libraries from %s", source_dir / "lib")
	# https://lukelogbook.tech/2018/01/25/merging-two-folders-in-python/
	for src_dir, _, files in os.walk(source_dir / "lib"):
		dst_dir = Path(src_dir.replace(str(source_dir / "lib"), str(config.lib_dir), 1))
		if not dst_dir.exists():
			os.makedirs(dst_dir)
		for file_ in files:
			if not (dst_dir / file_).exists():
				# avoid replacing files that might be currently loaded -> segfault
				shutil.copy2(Path(src_dir) / file_, dst_dir / file_)

	logger.info("Installing plugin from %s", source_dir / name)
	destination = config.plugin_dir / name
	if destination.exists():
		shutil.rmtree(destination)
	shutil.copytree(source_dir / name, destination)


def install_python_package(target_dir: str, package: Dict[str, str]) -> None:
	logger.info("Installing %r, version %r", package["name"], package["version"])
	pypath = get_python_path()
	try:
		# cmd = [pyversion, '-m', 'pip', 'install', f"{package['name']}>={package['version']}", "--target", target_dir]
		cmd = f"{pypath} -m pip install \"{package['name']}>={package['version']}\" --target \"{target_dir}\""
		logger.debug("Executing %r", cmd)
		result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
		logger.debug("success, command output\n%s", result.decode("utf-8"))
		return
	except subprocess.CalledProcessError as process_error:
		logger.warning("%s -m pip failed: %s", pypath, process_error, exc_info=True)
	logger.error("Could not install %s ... aborting", package["name"])
	raise RuntimeError(f"Could not install {package['name']} ... aborting")


def install_dependencies(path: str, target_dir: str) -> None:
	if (path / "requirements.txt").exists():
		logger.debug("Reading requirements.txt from %s", path)
		dependencies = pipreqs.parse_requirements(path / "requirements.txt")
	else:
		logger.debug("Generating requirements.txt from package %s", path)
		# candidates: python libraries (like requests, magic)
		candidates = pipreqs.get_pkg_names(pipreqs.get_all_imports(path))
		# dependencies: python package names (like Requests, python_magic)
		# this failes for packages not available at pypi.python.org (like opsicommon) -> those are ignored	TODO
		dependencies = pipreqs.get_imports_info(candidates, pypi_server="https://pypi.python.org/pypi/")  # proxy possible
		pipreqs.generate_requirements_file(path / "requirements.txt", dependencies, symbol=">=")
	logger.debug("Got dependencies: %s", dependencies)
	for dependency in dependencies:
		logger.debug("Checking dependency %s", dependency["name"])
		try:
			temp_module = importlib.import_module(dependency["name"])
			assert parse(temp_module.__version__) >= parse(dependency["version"])
			logger.debug(
				"Module %s present in version %s (required %s) - not installing",
				dependency["name"], temp_module.__version__, dependency["version"]
			)
		except (ImportError, AssertionError, AttributeError):
			install_python_package(target_dir, dependency)


def get_plugin_path(ctx: click.Context, name: str) -> str:
	plugin_dirs = ctx.obj["plugins"]
	logger.info("Trying to get plugin %r", name)
	logger.debug("Available plugins and their directories is: %s", plugin_dirs)
	if name not in plugin_dirs:
		raise ValueError(f"Plugin {name!r} not found.")
	return plugin_dirs[name]


@cli.command(short_help='Export plugin as .opsiplugin')
@click.argument('name', type=str)
@click.pass_context
def export(ctx: click.Context, name: str) -> None:
	"""
	opsi plugin export subcommand.
	This subcommand is used to export an installed opsi cli plugin.
	It is packaged as a .opsiplugin file which can be added to another
	instance of opsi cli via "plugin add". Also see "plugin list".
	"""
	logger.notice("Exporting command %r to %r", name, f"{name}.opsiplugin")
	path = get_plugin_path(ctx, name)
	logger.debug("Compressing plugin path %s", path)

	with zipfile.ZipFile(f"{name}.opsiplugin", "w", zipfile.ZIP_DEFLATED) as zfile:
		for root, _, files in os.walk(path):
			root = Path(root)
			base = root.relative_to(path)
			for single_file in files:
				zfile.write(str(root / single_file), arcname=str(Path(name) / base / single_file))


@cli.command(name="list", short_help='List imported plugins')
@click.pass_context
def list_command(ctx: click.Context) -> None:
	"""
	opsi plugin list subcommand.
	This subcommand lists all installed opsi cli plugins.
	"""
	for plugin_name in ctx.obj["plugins"].keys():
		print(plugin_name)  # check for validity?


@cli.command(short_help='Remove a plugin')
@click.argument('name', type=str)
@click.pass_context
def remove(ctx: click.Context, name: str) -> None:
	"""
	opsi plugin remove subcommand.
	This subcommand removes an installed opsi cli plugin. See "plugin list".
	"""
	path = get_plugin_path(ctx, name)
	if config.plugin_dir not in path.parents:
		raise ValueError(f"Attempt to remove plugin from invalid path {path!r} - Stopping.")
	logger.notice("Removing plugin %s", name)
	logger.debug("Deleting %s", path)
	shutil.rmtree(path)
