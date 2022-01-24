"""
opsi-cli Basic command line interface for opsi

plugin subcommand
"""

from packaging.version import parse
import importlib
import os
import shutil
import subprocess
import tempfile
import logging
import zipfile
import click
from pipreqs import pipreqs

from opsicli import COMMANDS_DIR, LIB_DIR


__version__ = "0.1.0"
logger = logging.getLogger()


def get_plugin_name():
	return "plugin"


@click.group(name="plugin", short_help="manage opsi CLI plugins")
@click.version_option(__version__, message="opsi plugin, version %(version)s")
@click.pass_context
def cli(ctx):  # pylint: disable=unused-argument
	"""
	opsi plugin subcommand.
	This is the long help.
	"""
	logger.info("plugin subcommand")


@cli.command(short_help='add new plugin (python package or .opsiplugin)')
@click.argument('path', type=click.Path(exists=True))
def add(path):
	"""
	opsi plugin add subsubcommand.
	This is the long help.
	"""
	with tempfile.TemporaryDirectory() as tmpdir:
		os.makedirs(os.path.join(tmpdir, "lib"), exist_ok=True)
		name = prepare_plugin(path, tmpdir)
		install_plugin(tmpdir, name)


def prepare_plugin(path, tmpdir):
	logger.info("inspecting plugin source %s", path)
	if os.path.exists(os.path.join(path, "__init__.py")):
		# normpath to be resistant against trailing separators
		name = os.path.basename(os.path.normpath(path))
		shutil.copytree(path, os.path.join(tmpdir, name))
	elif path.endswith(".opsiplugin"):
		with zipfile.ZipFile(path, "r") as zfile:
			zfile.extractall(tmpdir)
		name = os.path.basename(path)[:-11]  # cut the ".opsiplugin"
	else:
		raise ValueError(f"Invalid path given {path}")

	logger.info("retrieving libraries for new plugin")
	install_dependencies(os.path.join(tmpdir, name), os.path.join(tmpdir, "lib"))
	return name


def install_plugin(source_dir, name):
	logger.info("installing libraries")
	# https://lukelogbook.tech/2018/01/25/merging-two-folders-in-python/
	for src_dir, _, files in os.walk(os.path.join(source_dir, "lib")):
		dst_dir = src_dir.replace(os.path.join(source_dir, "lib"), LIB_DIR, 1)
		if not os.path.exists(dst_dir):
			os.makedirs(dst_dir)
		for file_ in files:
			src_file = os.path.join(src_dir, file_)
			dst_file = os.path.join(dst_dir, file_)
			if os.path.exists(dst_file):
				os.remove(dst_file)
			shutil.copy(src_file, dst_dir)

	logger.info("installing plugin")
	destination = os.path.join(COMMANDS_DIR, name)
	if os.path.exists(destination):
		shutil.rmtree(destination)
	shutil.copytree(os.path.join(source_dir, name), destination)


def install_dependencies(path, target_dir):
	if os.path.exists(os.path.join(path, "requirements.txt")):
		logger.debug("reading requirements.txt from %s", path)
		dependencies = pipreqs.parse_requirements(os.path.join(path, "requirements.txt"))
	else:
		logger.debug("generating requirements.txt from package %s", path)
		# candidates: python libraries (like requests, magic)
		candidates = pipreqs.get_pkg_names(pipreqs.get_all_imports(path))
		# dependencies: python package names (like Requests, python_magic)
		# this failes for packages not available at pypi.python.org (like opsicommon) -> those are ignored	TODO
		dependencies = pipreqs.get_imports_info(candidates, pypi_server="https://pypi.python.org/pypi/")  # proxy possible
		pipreqs.generate_requirements_file(os.path.join(path, "requirements.txt"), dependencies, symbol=">=")
	logger.debug("got dependencies: %s", dependencies)
	for dependency in dependencies:
		try:
			logger.debug("checking dependency %s", dependency["name"])
			temp_module = importlib.import_module(dependency["name"])
			assert parse(temp_module.__version__) >= parse(dependency["version"])
			logger.debug(
				"module %s present in version %s (required %s) - not installing",
				dependency["name"], temp_module.__version__, dependency["version"]
			)
		except (ImportError, AssertionError, AttributeError):
			try:
				logger.info("installing %s, version %s", dependency["name"], dependency["version"])
				subprocess.check_call(["python3", '-m', 'pip', 'install', f"{dependency['name']}>={dependency['version']}", f"--target={target_dir}"])
			except subprocess.CalledProcessError:
				try:
					logger.warning("python3 -m pip failed, trying python -m pip")
					subprocess.check_call(["python", '-m', 'pip', 'install', f"{dependency['name']}>={dependency['version']}", f"--target={target_dir}"])
				except subprocess.CalledProcessError as process_error:
					logger.error("Could not install %s ... aborting", dependency["name"])
					raise process_error


def get_plugin_path(ctx, name):
	plugin_dirs = ctx.obj["plugins"]
	logger.info("trying to get plugin %s", name)
	logger.debug("list of available plugins is: %s", plugin_dirs)
	if name not in plugin_dirs:
		raise ValueError(f"Plugin {name} not found.")
	return plugin_dirs[name]


@cli.command(short_help='export plugin as .opsiplugin')
@click.argument('name', type=str)
@click.pass_context
def export(ctx, name):
	"""
	opsi plugin export subsubcommand.
	This is the long help.
	"""
	logger.notice("exporting command %s to %s", name, f"{name}.opsiplugin")
	path = get_plugin_path(ctx, name)
	logger.debug("compressing plugin path %s", path)

	arcname = os.path.split(path)[1]
	with zipfile.ZipFile(f"{name}.opsiplugin", "w", zipfile.ZIP_DEFLATED) as zfile:
		for root, _, files in os.walk(path):
			base = os.path.relpath(root, start=path)
			for single_file in files:
				zfile.write(os.path.join(root, single_file), arcname=os.path.join(arcname, base, single_file))


@cli.command(name="list", short_help='list imported plugins')
@click.pass_context
def list_command(ctx):
	"""
	opsi plugin list subsubcommand.
	This is the long help.
	"""
	for plugin_name in ctx.obj["plugins"].keys():
		print(plugin_name)  # check for validity?


@cli.command(short_help='removes a plugin')
@click.argument('name', type=str)
@click.pass_context
def remove(ctx, name):
	"""
	opsi plugin remove subsubcommand.
	This is the long help.
	"""
	path = get_plugin_path(ctx, name)
	assert COMMANDS_DIR in path  # to be sure...
	logger.notice("removing plugin %s", name)
	logger.debug("deleting %s", path)
	shutil.rmtree(path)
