import click
import os

__version__ = "0.1.0"

#https://click.palletsprojects.com/en/7.x/commands/#custom-multi-commands
plugin_folder = os.path.join(os.path.dirname(__file__), 'commands')

class OpsiCLI(click.MultiCommand):

	def list_commands(self, ctx):
		rv = []
		for filename in os.listdir(plugin_folder):
			if filename.endswith('.py'):
				rv.append(filename[:-3])
		rv.sort()
		return rv

	def get_command(self, ctx, name):
		if name == "__init__":
			return None 	# cli is called without subcommand
		ns = {}
		fn = os.path.join(plugin_folder, name + '.py')
		with open(fn) as f:
			code = compile(f.read(), fn, 'exec')
			eval(code, ns, ns)
		return ns['cli']

@click.command(cls=OpsiCLI)
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(f"{__version__}", message="opsiCLI, version %(version)s")
def cli():
	"""
	opsi Command Line Interface\n
	Subcommands are dynamically loaded from a subfolder
	"""
	print("cli was called")