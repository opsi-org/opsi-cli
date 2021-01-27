import logging
import requests
import magic		# pylint: disable=E0401
import click

__version__ = "0.1.0"
logger = logging.getLogger()


def get_plugin_name():
	return "dummy"


@click.group(name="dummy", short_help="short help for dummy")
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(__version__, message="opsi support, version %(version)s")
def cli():
	"""
	opsi dummy subcommand.
	This is the long help.
	"""
	logger.info("dummy subcommand")


@cli.command(short_help='short help for subdummy')
def subdummy():
	"""
	opsi dummy subdummy subsubcommand.
	This is the long help.
	"""
	logger.info("subdummy subsubcommand")
	magic_resolver = magic.Magic(mime=True, uncompress=True)
	print(magic_resolver.from_file('opsi-dev-tool.yml'))
