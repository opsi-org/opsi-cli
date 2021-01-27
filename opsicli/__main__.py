import os
import sys
import importlib
import click

from opsicli import plugin, COMMANDS_DIR, LIB_DIR, init_logging, logger

__version__ = "0.1.0"


#https://click.palletsprojects.com/en/7.x/commands/#custom-multi-commands
class OpsiCLI(click.MultiCommand):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.plugin_folders = [COMMANDS_DIR]
		self.external_lib_folder = LIB_DIR
		self.plugin_modules = {}
		if not os.path.exists(COMMANDS_DIR):
			os.makedirs(COMMANDS_DIR, exist_ok=True)
		if not os.path.exists(LIB_DIR):
			os.makedirs(LIB_DIR, exist_ok=True)


	def register_commands(self, ctx):
		if self.external_lib_folder not in sys.path:
			sys.path.append(self.external_lib_folder)

		if ctx.obj is None:
			ctx.obj = {}
		result = []
		for folder in self.plugin_folders:
			for filename in os.listdir(folder):
				path = os.path.join(folder, filename, "__init__.py")
				if os.path.exists(path):
					spec = importlib.util.spec_from_file_location("temp", path)
					new_plugin = importlib.util.module_from_spec(spec)
					spec.loader.exec_module(new_plugin)
					name = new_plugin.get_plugin_name()
					self.plugin_modules[name] = new_plugin

					# Caution: loglevel does not affect this message
					logger.debug('Adding command %s', name)
					result.append(name)

					# add reference to plugin_modules into context to access it in plugin export
					# https://click.palletsprojects.com/en/7.x/complex/#the-root-command
					ctx.obj.update({name : os.path.join(folder, filename)})

		self.plugin_modules["plugin"] = plugin


	def list_commands(self, ctx):
		if not self.plugin_modules:
			self.register_commands(ctx)
		return sorted(self.plugin_modules.keys())


	def get_command(self, ctx, cmd_name):
		if not cmd_name in self.plugin_modules:
			self.register_commands(ctx)
			if not cmd_name in self.plugin_modules:
				raise ValueError(f"invalid command {cmd_name}")
		return self.plugin_modules[cmd_name].cli


@click.command(cls=OpsiCLI)
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(f"{__version__}", message="opsiCLI, version %(version)s")
@click.option('--log-level', "-l", default="warning", type=click.Choice(['critical', 'error', "warning", "info", "debug"]))
def main(log_level):
	"""
	opsi Command Line Interface\n
	Subcommands are dynamically loaded from a subfolder
	"""
	init_logging(log_level)
	logger.info("cli was called")
