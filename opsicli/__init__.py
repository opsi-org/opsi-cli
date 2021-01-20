import os
import importlib
import click

__version__ = "0.1.0"

#https://click.palletsprojects.com/en/7.x/commands/#custom-multi-commands
class OpsiCLI(click.MultiCommand):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.plugin_folders = [os.path.expanduser("~/.local/lib/opsicli/commands")]
		self.plugin_modules = []
		self.plugin_info = {}

	def register_commands(self):
		result = []
		for folder in self.plugin_folders:
			for filename in os.listdir(folder):
				path = os.path.join(folder, filename, "__init__.py")
				if os.path.exists(path):
					spec = importlib.util.spec_from_file_location("dummy", path)
					self.plugin_modules.append(importlib.util.module_from_spec(spec))
					spec.loader.exec_module(self.plugin_modules[-1])
					info = self.plugin_modules[-1].get_plugin_info()
					self.plugin_info[info["name"]] = info
					self.plugin_info[info["name"]]["index"] = len(self.plugin_modules) - 1

					#print(f'Adding command {info["name"]}')
					result.append(info["name"])

	def list_commands(self, ctx):
		if not self.plugin_info:
			self.register_commands()
		return sorted(self.plugin_info.keys())

	def get_command(self, ctx, cmd_name):
		if not cmd_name in self.plugin_info:
			self.register_commands()
			if not cmd_name in self.plugin_info:
				raise ValueError(f"invalid command {cmd_name}")
		index = self.plugin_info[cmd_name]["index"]
		return self.plugin_modules[index].cli


@click.command(cls=OpsiCLI)
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(f"{__version__}", message="opsiCLI, version %(version)s")
def cli():
	"""
	opsi Command Line Interface\n
	Subcommands are dynamically loaded from a subfolder
	"""
	print("cli was called")
