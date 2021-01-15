import os
import click

__version__ = "0.1.0"

#https://click.palletsprojects.com/en/7.x/commands/#custom-multi-commands
plugin_folder = os.path.join(os.path.dirname(__file__), 'commands')

class OpsiCLI(click.MultiCommand):
	def list_commands(self, ctx):
		result = []
		for filename in os.listdir(plugin_folder):
			if not os.path.isdir(os.path.join(plugin_folder, filename)):
				continue
			if os.path.exists(os.path.join(plugin_folder, filename, "__init__.py")):
				result.append(filename)
		result.sort()
		return result

	def get_command(self, ctx, cmd_name):
		if cmd_name == "__init__":
			return None 	# cli is called without subcommand
		namespace = {}
		filename = os.path.join(plugin_folder, cmd_name, '__init__.py')
		with open(filename) as command_file:
			code = compile(command_file.read(), filename, 'exec')
			eval(code, namespace, namespace)		# pylint: disable=W0123
		return namespace['cli']

@click.command(cls=OpsiCLI)
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(f"{__version__}", message="opsiCLI, version %(version)s")
def cli():
	"""
	opsi Command Line Interface\n
	Subcommands are dynamically loaded from a subfolder
	"""
	print("cli was called")
