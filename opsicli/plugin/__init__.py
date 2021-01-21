import os
import shutil
import click
import subprocess
from pipreqs import pipreqs

from opsicli import COMMANDS_DIR, LIB_DIR


__version__ = "0.1.0"


def get_plugin_name():
	return "plugin"


@click.group(short_help="manage opsi CLI plugins")
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(__version__, message="opsi plugin, version %(version)s")
def cli():
	"""
	opsi plugin subcommand.
	This is the long help.
	"""
	print("plugin subcommand")


@cli.command(short_help='register a new plugin')
@click.argument('path')
def register(path):
	"""
	opsi plugin register subsubcommand.
	This is the long help.
	"""
	candidates = pipreqs.get_all_imports(path)
	candidates = pipreqs.get_pkg_names(candidates)
	dependencies = pipreqs.get_imports_info(candidates, pypi_server="https://pypi.python.org/pypi/")	#proxy possible
	for dependency in dependencies:
		try:
			print("installing", dependency["name"], "version", dependency["version"])
			subprocess.check_call(["python3", '-m', 'pip', 'install', f"{dependency['name']}=={dependency['version']}", f"--target={LIB_DIR}"])
		except subprocess.CalledProcessError as process_error:
			print("Could not install ", dependency["name"])
			print(process_error)
			print("... aborting")
			exit(1)

	dirname = os.path.basename(os.path.dirname(path))
	print(f"copying {path} to {os.path.join(COMMANDS_DIR, dirname)}")
	shutil.copytree(path, os.path.join(COMMANDS_DIR, dirname))
