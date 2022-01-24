"""
opsi-cli Basic command line interface for opsi

dummy command - proof of concept
"""

import requests
import netifaces		# pylint: disable=import-error
import click

from opsicommon.logging import logger

__version__ = "0.1.0"


def get_plugin_name():
	return "dummy"


@click.group(name="dummy", short_help="short help for dummy")
@click.version_option(__version__, message="dummy plugin test, version %(version)s")
def cli():
	"""
	opsi dummy subcommand.
	This is the long help.
	"""
	logger.info("dummy subcommand")


@cli.command(short_help='short help for subdummy')
def libtest():
	"""
	opsi dummy subdummy subsubcommand.
	This is the long help.
	"""
	logger.info("subdummy subsubcommand")
	print(netifaces.gateways())
	print(requests.get("https://opsi.org"))
