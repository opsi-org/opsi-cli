import click

__version__ = "0.1.0"

@click.group()
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(f"{__version__}", message="opsi support, version %(version)s")
def cli():
	print("support subcommand")

@cli.command()
def ticket():
	print("ticket subcommand")