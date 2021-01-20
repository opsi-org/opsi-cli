#import requests
import click

__version__ = "0.1.0"


def get_plugin_name():
	return "dummy"


@click.group(short_help="short help for dummy")
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(__version__, message="opsi support, version %(version)s")
def cli():
	"""
	opsi dummy subcommand.
	This is the long help.
	"""
	print("dummy subcommand")


@cli.command(short_help='short help for subdummy')
def subdummy():
	"""
	opsi dummy subdummy subsubcommand.
	This is the long help.
	"""
	print("subdummy subsubcommand")
