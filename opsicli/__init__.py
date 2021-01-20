import os
import importlib
import click

__version__ = "0.1.0"

#https://click.palletsprojects.com/en/7.x/commands/#custom-multi-commands
class OpsiCLI(click.MultiCommand):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.plugin_folders = [os.path.expanduser("~/.local/lib/opsicli/commands")]
		self.plugin_modules = {}

	def register_commands(self):
		result = []
		for folder in self.plugin_folders:
			for filename in os.listdir(folder):
				path = os.path.join(folder, filename, "__init__.py")
				if os.path.exists(path):
					spec = importlib.util.spec_from_file_location("dummy", path)
					new_plugin = importlib.util.module_from_spec(spec)
					spec.loader.exec_module(new_plugin)
					name = new_plugin.get_plugin_name()
					self.plugin_modules[name] = new_plugin

					#print(f'Adding command {name}')
					result.append(name)

	def list_commands(self, ctx):
		if not self.plugin_modules:
			self.register_commands()
		return sorted(self.plugin_modules.keys())

	def get_command(self, ctx, cmd_name):
		if not cmd_name in self.plugin_modules:
			self.register_commands()
			if not cmd_name in self.plugin_modules:
				raise ValueError(f"invalid command {cmd_name}")
		return self.plugin_modules[cmd_name].cli


@click.command(cls=OpsiCLI)
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(f"{__version__}", message="opsiCLI, version %(version)s")
def cli():
	"""
	opsi Command Line Interface\n
	Subcommands are dynamically loaded from a subfolder
	"""
	print("cli was called")
