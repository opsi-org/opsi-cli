# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

plugin handling
"""
import os
import sys
import shutil
import zipfile
import subprocess
import importlib
from typing import Dict, List, Optional
from pathlib import Path
from urllib.parse import quote, unquote
from importlib._bootstrap import BuiltinImporter  # type: ignore[import]

from click import Command
from packaging.version import parse
from pipreqs import pipreqs  # type: ignore[import]

from opsicommon.utils import Singleton  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.config import config, get_python_path


PLUGIN_EXTENSION = "opsicliplug"


# this creates the plugin command and libs in tmp
def prepare_plugin(path: Path, tmpdir: Path) -> str:
	logger.info("Inspecting plugin source %s", path)
	name = path.stem
	if (path / "__init__.py").exists():
		shutil.copytree(path, tmpdir / name)
	elif path.suffix == f".{PLUGIN_EXTENSION}":
		with zipfile.ZipFile(path, "r") as zfile:
			zfile.extractall(tmpdir)
	else:
		raise ValueError(f"Invalid path given {path!r}")

	logger.info("Retrieving libraries for new plugin")
	install_dependencies(tmpdir / name, tmpdir / "lib")
	return name


# this copies the prepared plugin from tmp to LIB_DIR
def install_plugin(source_dir: Path, name: str) -> None:
	logger.info("Installing libraries from %s", source_dir / "lib")
	# https://lukelogbook.tech/2018/01/25/merging-two-folders-in-python/
	for src_dir_string, _, files in os.walk(source_dir / "lib"):
		src_dir = Path(src_dir_string)
		dst_dir = config.lib_dir / src_dir.relative_to(source_dir / "lib")
		if not dst_dir.exists():
			dst_dir.mkdir(parents=True, exist_ok=True)
		for file_ in files:
			if not (dst_dir / file_).exists():
				# avoid replacing files that might be currently loaded -> segfault
				shutil.copy2(src_dir / file_, dst_dir / file_)

	logger.info("Installing plugin from %s", source_dir / name)
	destination = config.plugin_dirs[-1] / name
	if destination.exists():
		shutil.rmtree(destination)
	shutil.copytree(source_dir / name, destination)


def install_python_package(target_dir: Path, package: Dict[str, str]) -> None:
	logger.info("Installing %r, version %r", package["name"], package["version"])
	pypath = get_python_path()
	try:
		# cmd = [pyversion, '-m', 'pip', 'install', f"{package['name']}>={package['version']}", "--target", target_dir]
		cmd = f"\"{pypath}\" -m pip install \"{package['name']}>={package['version']}\" --target \"{target_dir}\""
		logger.debug("Executing %r", cmd)
		result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
		logger.debug("success, command output\n%s", result.decode("utf-8"))
		return
	except subprocess.CalledProcessError as process_error:
		logger.error("Command %r failed ... aborting: %s", cmd, process_error, exc_info=True)
		raise RuntimeError(f"Could not install {package['name']!r} ... aborting") from process_error


def install_dependencies(path: Path, target_dir: Path) -> None:
	if (path / "requirements.txt").exists():
		logger.debug("Reading requirements.txt from %s", path)
		dependencies = pipreqs.parse_requirements(path / "requirements.txt")
	else:
		logger.debug("Generating requirements.txt from package %s", path)
		# candidates: python libraries (like requests, magic)
		candidates = pipreqs.get_pkg_names(pipreqs.get_all_imports(path))
		# dependencies: python package names (like Requests, python_magic)
		# this failes for packages not available at pypi.python.org (like opsicommon) -> those are ignored	TODO
		dependencies = pipreqs.get_imports_info(candidates, pypi_server="https://pypi.python.org/pypi/")  # proxy possible
		pipreqs.generate_requirements_file(path / "requirements.txt", dependencies, symbol=">=")
	logger.debug("Got dependencies: %s", dependencies)
	for dependency in dependencies:
		logger.debug("Checking dependency %s", dependency["name"])
		try:
			temp_module = importlib.import_module(dependency["name"])
			assert parse(temp_module.__version__) >= parse(dependency["version"])
			logger.debug(
				"Module %r present in version %s (required %s) - not installing",
				dependency["name"],
				temp_module.__version__,
				dependency["version"],
			)
		except (ImportError, AssertionError, AttributeError):
			install_python_package(target_dir, dependency)


class OPSICLIPlugin:
	id: str = ""  # pylint: disable=invalid-name
	name: str = ""
	description: str = ""
	version: str = ""
	cli: Optional[Command] = None

	def __init__(self, path: Path) -> None:  # pylint: disable=redefined-builtin
		self.path = path
		self.data_path = self.path / "data"

	def on_load(self) -> None:  # pylint: disable=no-self-use,unused-argument
		"""Called after loading the plugin"""
		return

	def on_unload(self) -> None:  # pylint: disable=no-self-use,unused-argument
		"""Called before unloading the plugin"""
		return


class PluginImporter(BuiltinImporter):
	@classmethod
	def find_spec(cls, fullname, path=None, target=None):
		if not fullname.startswith("opsicli.addon"):
			return None
		plugin_path = unquote(fullname.split("_", 1)[1])
		init_path = os.path.join(plugin_path, "python", "__init__.py")
		if not os.path.exists(init_path):
			return None
		return importlib.util.spec_from_file_location(fullname, init_path)


sys.meta_path.append(PluginImporter)  # type: ignore[arg-type]


class PluginManager(metaclass=Singleton):  # pylint: disable=too-few-public-methods
	def __init__(self) -> None:
		self._plugins: Dict[str, OPSICLIPlugin] = {}

	@classmethod
	def module_name(cls, plugin_path: Path) -> str:
		return f"opsicli.addon_{quote(str(plugin_path))}"

	@property
	def plugins(self) -> List[OPSICLIPlugin]:
		return list(self._plugins.values())

	def get_plugin(self, plugin_id: str) -> OPSICLIPlugin:
		return self._plugins[plugin_id]

	def load_plugin(self, plugin_dir: Path) -> None:
		logger.info("Loading plugin from '%s'", plugin_dir)
		module_name = self.module_name(plugin_dir)
		if module_name in sys.modules:
			reload = []
			for sys_module in list(sys.modules):
				if sys_module.startswith(module_name):
					reload.append(sys_module)
			reload.sort(reverse=True)
			for sys_module in reload:
				importlib.reload(sys.modules[sys_module])
			module = sys.modules[module_name]
		else:
			module = importlib.import_module(module_name)

		for cls in module.__dict__.values():
			if isinstance(cls, type) and issubclass(cls, OPSICLIPlugin) and cls != OPSICLIPlugin and cls.id:
				logger.notice("Loading plugin %r (%s)", cls.id, cls.name)
				self._plugins[cls.id] = cls(plugin_dir)
				self._plugins[cls.id].on_load()
				# Only one class per module
				break

	def load_plugins(self) -> None:
		if self._plugins:
			return
		logger.debug("Loading plugins")
		self._plugins = {}
		for plugin_base_dir in config.plugin_dirs:
			if not plugin_base_dir.exists():
				logger.debug("Plugin dir '%s' not found", plugin_base_dir)
				continue
			logger.info("Loading plugins from dir '%s'", plugin_base_dir)
			for plugin_dir in plugin_base_dir.iterdir():
				init_path = plugin_dir / "python" / "__init__.py"
				if not init_path.exists():
					continue
				try:
					self.load_plugin(plugin_dir=plugin_dir)
				except Exception as err:  # pylint: disable=broad-except
					logger.error("Failed to load plugin from '%s': %s", plugin_dir, err, exc_info=True)

	def unload_plugin(self, plugin_id: str) -> None:
		if plugin_id not in self._plugins:
			raise ValueError(f"Plugin '{plugin_id} not loaded")
		self._plugins[plugin_id].on_unload()
		del self._plugins[plugin_id]

	def unload_plugins(self) -> None:
		for plugin in list(self._plugins.values()):
			self.unload_plugin(plugin.id)

	def reload_plugin(self, plugin_id: str) -> None:
		if plugin_id not in self._plugins:
			raise ValueError(f"Plugin '{plugin_id} not loaded")
		addon = self._plugins[plugin_id]
		path = addon.path
		self.unload_plugin(plugin_id)
		self.load_plugin(path)

	def reload_plugins(self):
		self.unload_plugins()
		self.load_plugins()


plugin_manager = PluginManager()
