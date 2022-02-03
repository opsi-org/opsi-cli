"""
opsi-cli Basic command line interface for opsi

dummy command - proof of concept
"""

from typing import Any, Dict
import requests
import netifaces		# pylint: disable=import-error
import click

from opsicommon.logging import logger

__version__ = "0.1.0"


def get_plugin_info() -> Dict[str,Any]:
	return {
		"name": "dummy",
		"version": __version__
	}


@click.group(name="dummy", short_help="short help for dummy")
@click.version_option(__version__, message="dummy plugin test, version %(version)s")
def cli() -> None:
	"""
	opsi dummy command.
	This is the long help.
	"""
	logger.trace("dummy command")


@cli.command(short_help='short help for subdummy')
def libtest() -> None:
	"""
	opsi dummy subdummy subcommand.
	This is the long help.
	"""
	print(netifaces.gateways())
	print(requests.get("https://opsi.org"))
