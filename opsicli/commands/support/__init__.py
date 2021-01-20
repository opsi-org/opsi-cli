import click

__version__ = "0.1.0"

def get_plugin_info():
	return {
		"name" : "support",
		"subcommands" : ["ticket"],
		"help" : "this is the support help"
	}

def get_plugin_name():
	return "support"

@click.group(short_help='short help for support')
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(__version__, message="opsi support, version %(version)s")
def cli():
	print("support subcommand")

@cli.command(short_help='short help for ticket')
def ticket():
	print("ticket subcommand")
