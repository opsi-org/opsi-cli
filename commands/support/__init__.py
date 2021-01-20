import click

__version__ = "0.1.0"


def get_plugin_name():
	return "support"


@click.group(short_help="short help for support")
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(__version__, message="opsi support, version %(version)s")
def cli():
	"""
	opsi support subcommand.
	This is the long help.
	"""
	print("support subcommand")


@cli.command(short_help='short help for ticket')
def ticket():
	"""
	opsi support ticket subsubcommand.
	This is the long help.
	"""
	print("ticket subsubcommand")
