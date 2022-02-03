"""
opsi-cli Basic command line interface for opsi

Main command
"""

from typing import List, Dict
from types import ModuleType
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
import click

from opsicommon.logging import logger, logging_config, DEFAULT_COLORED_FORMAT  # type: ignore[import]

from opsicli import plugin, prepare_cli_paths, prepare_context, __version__
from opsicli.config import config


# https://click.palletsprojects.com/en/7.x/commands/#custom-multi-commands
class OpsiCLI(click.MultiCommand):
	def __init__(self, *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)
		self.plugin_modules: Dict[str, ModuleType] = {}

	def register_plugins(self, ctx: click.Context) -> None:
		prepare_cli_paths()
		prepare_context(ctx)

		logger.debug("Initializing plugins from dir %r", config.plugin_dir)
		for dirname in config.plugin_dir.iterdir():
			try:
				self.load_plugin(ctx, dirname)
			except ImportError as import_error:
				logger.error("Could not load plugin from %r: %s", dirname, import_error, exc_info=True)
				raise  # continue

		self.plugin_modules["plugin"] = plugin

	def load_plugin(self, ctx: click.Context, dirname: Path) -> None:
		path = config.plugin_dir / dirname / "__init__.py"
		if not path.exists():
			raise ImportError(f"{config.plugin_dir / dirname} does not have __init__.py")
		spec = spec_from_file_location("temp", path)
		if not spec:
			raise ImportError(f"{config.plugin_dir / dirname / '__init__.py'} is not a valid python module")
		new_plugin = module_from_spec(spec)
		if not spec.loader:
			raise ImportError(f"{config.plugin_dir / dirname / '__init__.py'} spec does not have valid loader")
		spec.loader.exec_module(new_plugin)
		try:
			name = new_plugin.get_plugin_info()["name"]
		except (AttributeError, KeyError) as error:
			raise ImportError(f"{config.plugin_dir / dirname} does not have a valid get_plugin_info method (key name required)") from error
		self.plugin_modules[name] = new_plugin

		logger.debug("Adding plugin %r", name)
		# add reference to plugin modules into context to access it in plugin management
		ctx.obj["plugins"][name] = config.plugin_dir / dirname

	def list_commands(self, ctx: click.Context) -> List[str]:
		if not self.plugin_modules:
			self.register_plugins(ctx)
		return sorted(self.plugin_modules.keys())

	def get_command(self, ctx: click.Context, cmd_name: str) -> click.core.Command:
		if cmd_name not in self.plugin_modules:
			self.register_plugins(ctx)
			if cmd_name not in self.plugin_modules:
				raise ValueError(f"invalid command {cmd_name!r}")
		return self.plugin_modules[cmd_name].cli


@click.command(cls=OpsiCLI)
@click.version_option(f"{__version__}", message="opsiCLI, version %(version)s")
@click.option("--log-level", "-l", default=4, type=click.IntRange(min=1, max=9))
@click.option("--service-url", envvar="OPSI_SERVICE_URL", default="https://localhost:4447", type=str)
@click.option("--username", "-u", envvar="OPSI_USERNAME", type=str)
@click.option("--password", "-p", envvar="OPSI_PASSWORD", type=str)
@click.pass_context
def main(ctx: click.Context, log_level: int, username: str, password: str, service_url: str) -> None:
	"""
	opsi Command Line Interface\n
	plugins are dynamically loaded from a subfolder
	"""

	logging_config(stderr_level=log_level, stderr_format=DEFAULT_COLORED_FORMAT)

	if not ctx.obj:  # stacked execution in pytest circumvents register_plugins -> explicit call here
		logger.notice("Explicitely calling register_plugins")
		assert isinstance(ctx.command, OpsiCLI)  # generic command does not have register_plugins
		ctx.command.register_plugins(ctx)
	ctx.obj.update({"username": username, "password": password, "service_url": service_url})
	logger.trace("cli was called")
