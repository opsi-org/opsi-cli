import os
import shutil
import subprocess
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
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(__version__, message="opsi plugin, version %(version)s")
def cli():
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
	if os.path.exists(os.path.join(path, "__init__.py")):
		add_from_package(path)
	elif path.endswith(".opsiplugin"):
		add_from_opsiplugin(path)
	else:
		raise ValueError(f"Invalid path given {path}")


def add_from_package(path):
	install_dependencies(path)

	dirname = os.path.basename(os.path.dirname(path + "/"))
	logger.info("copying %s to %s", path, os.path.join(COMMANDS_DIR, dirname))
	if os.path.exists(os.path.join(COMMANDS_DIR, dirname)):
		logger.debug("overwriting existing plugin code for %s", dirname)
		shutil.rmtree(os.path.join(COMMANDS_DIR, dirname))
	shutil.copytree(path, os.path.join(COMMANDS_DIR, dirname))


def add_from_opsiplugin(path):
	with zipfile.ZipFile(path, "r") as zfile:
		zfile.extractall(COMMANDS_DIR)
	name = os.path.basename(path)[:-11]		# cut the ".opsiplugin"
	install_dependencies(os.path.join(COMMANDS_DIR, name))


def install_dependencies(path):
	if os.path.exists(os.path.join(path, "requirements.txt")):
		logger.debug("reading requirements.txt from %s", path)
		dependencies = pipreqs.parse_requirements(os.path.join(path, "requirements.txt"))
	else:
		logger.debug("generating requirements.txt from package %s", path)
		candidates = pipreqs.get_pkg_names(pipreqs.get_all_imports(path))
		dependencies = pipreqs.get_imports_info(candidates, pypi_server="https://pypi.python.org/pypi/")	#proxy possible
		pipreqs.generate_requirements_file(os.path.join(path, "requirements.txt"), dependencies)
	for dependency in dependencies:
		try:
			logger.info("installing %s, version %s", dependency["name"], dependency["version"])
			subprocess.check_call(["python3", '-m', 'pip', 'install', f"{dependency['name']}=={dependency['version']}", f"--target={LIB_DIR}"])
		except subprocess.CalledProcessError as process_error:
			logger.error("Could not install %s ... aborting", dependency["name"])
			raise process_error


@cli.command(short_help='export plugin as .opsiplugin')
@click.argument('name', type=str)
def export(name):
	"""
	opsi plugin export subsubcommand.
	This is the long help.
	"""
	plugin_dirs = click.get_current_context().obj
	if not name in plugin_dirs:
		raise ValueError(f"Plugin {name} (requested to export) not found.")

	logger.info("exporting command %s to %s", name, f"{name}.opsiplugin")
	arcname = os.path.split(plugin_dirs[name])[1]
	with zipfile.ZipFile(f"{name}.opsiplugin", "w", zipfile.ZIP_DEFLATED) as zfile:
		for root, _, files in os.walk(plugin_dirs[name]):
			base = os.path.relpath(root, start=plugin_dirs[name])
			for single_file in files:
				zfile.write(os.path.join(root, single_file), arcname=os.path.join(arcname, base, single_file))
