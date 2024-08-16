# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

plugin handling
"""

import importlib
import os
import shutil
import sys
import warnings
import zipfile
from importlib._bootstrap import BuiltinImporter  # type: ignore[import]
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

from click import Command  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]
from opsicommon.utils import Singleton  # type: ignore[import]
from packaging.version import parse

from opsicli.config import COMPLETION_MODE, config

logger = get_logger("opsicli")

PLUGIN_EXTENSION = "opsicliplug"


class OPSICLIPlugin:
	name: str = ""
	description: str = ""
	version: str = ""
	cli: Command | None = None
	flags: list[str] = []

	def __init__(self, path: Path) -> None:
		self.path = path
		self.data_path = self.path / "data"

	def on_load(self) -> None:
		"""Called after loading the plugin"""
		return

	def __str__(self) -> str:
		"""Return information in string form"""
		return f"{self.path.name}_{self.version}({self.flags})"

	def get_module_name(self) -> str:
		return PluginManager.module_name(self.path)

	def get_module(self) -> ModuleType:
		return sys.modules[self.get_module_name()]


class PluginImporter(BuiltinImporter):
	@classmethod
	def find_spec(cls, fullname: str, path: None = None, target: None = None) -> ModuleSpec | None:
		if not fullname.startswith("opsicli.addon"):
			return None
		plugin_path = bytes.fromhex(fullname.split("_", 1)[1]).decode("utf-8")
		init_path = os.path.join(plugin_path, "python", "__init__.py")
		logger.debug("Searching spec for %s", init_path)
		if not os.path.exists(init_path):
			return None
		return importlib.util.spec_from_file_location(fullname, init_path)


sys.meta_path.append(PluginImporter)  # type: ignore[arg-type]


class PluginManager(metaclass=Singleton):
	def __init__(self) -> None:
		pass

	@classmethod
	def module_name(cls, plugin_path: Path) -> str:
		quoted_path = str(plugin_path).encode("utf-8").hex()
		return f"opsicli.addon_{quoted_path}"

	@property
	def plugins(self) -> list[str]:
		return self.get_plugins([config.plugin_bundle_dir, config.plugin_system_dir, config.plugin_user_dir])

	def get_plugins(self, dirs: list[Path]) -> list[str]:
		plugin_ids = []
		for plugin_base_dir in dirs:
			if not plugin_base_dir:
				continue
			if not plugin_base_dir.exists():
				logger.debug("Plugin dir '%s' not found", plugin_base_dir)
				continue
			logger.debug("Checking plugins from dir '%s'", plugin_base_dir)
			for plugin_dir in plugin_base_dir.iterdir():
				if (plugin_dir / "python" / "__init__.py").exists() and plugin_dir.name not in plugin_ids:
					plugin_ids.append(plugin_dir.name)
		return plugin_ids

	def load_plugin_module(self, plugin_dir: Path) -> ModuleType:
		if (config.python_lib_dir / plugin_dir.name).exists() and str(config.python_lib_dir / plugin_dir.name) not in sys.path:
			logger.debug("Prepending to sys.path: %s", config.python_lib_dir / plugin_dir.name)
			sys.path.insert(0, str(config.python_lib_dir / plugin_dir.name))
		logger.debug("Extracting plugin object from '%s'", plugin_dir)
		logger.debug("sys.path = %s", sys.path)
		module_name = self.module_name(plugin_dir)
		if module_name in sys.modules:
			reload = []
			for sys_module in list(sys.modules):
				if sys_module.startswith(module_name):
					reload.append(sys_module)
			reload.sort(reverse=True)
			for sys_module in reload:
				importlib.reload(sys.modules[sys_module])
			return sys.modules[module_name]
		return importlib.import_module(self.module_name(plugin_dir))

	def get_plugin_dir(self, name: str) -> Path:
		for plugin_base_dir in (config.plugin_bundle_dir, config.plugin_system_dir, config.plugin_user_dir):
			if not plugin_base_dir:
				continue
			if not plugin_base_dir.exists():
				logger.debug("Plugin dir '%s' not found", plugin_base_dir)
				continue
			if (plugin_base_dir / name).exists():
				logger.debug("Found plugin %s at %s", name, plugin_base_dir / name)
				return plugin_base_dir / name
		raise FileNotFoundError(f"Did not find plugin '{name}'.")

	def load_plugin(self, name: str) -> OPSICLIPlugin:
		plugin_dir = self.get_plugin_dir(name)
		module = self.load_plugin_module(plugin_dir)
		for cls in module.__dict__.values():
			if isinstance(cls, type) and issubclass(cls, OPSICLIPlugin) and cls != OPSICLIPlugin:
				logger.info("Loading plugin %r (name=%s, cli=%s)", plugin_dir.name, cls.name, cls.cli)
				plugin = cls(plugin_dir)
				if not COMPLETION_MODE:
					plugin.on_load()
				# Only one class per module
				return plugin
		raise RuntimeError(f"Failed to load plugin '{name}'.")


plugin_manager = PluginManager()


def replace_data(string: str, replacements: dict[str, str]) -> str:
	for key, value in replacements.items():
		string = string.replace(key, value)
	return string


def prepare_plugin(path: Path, tmpdir: Path) -> str:
	"""Creates the plugin and libs in tmp"""
	logger.info("Inspecting plugin source '%s'", path)
	plugin_id = path.stem
	if (path / "python" / "__init__.py").exists():
		shutil.copytree(path, tmpdir / plugin_id)
	elif path.suffix == f".{PLUGIN_EXTENSION}":
		with zipfile.ZipFile(path, "r") as zfile:
			zfile.extractall(tmpdir)
	else:
		raise ValueError(f"Invalid path given '{path}'")

	logger.info("Retrieving libraries for new plugin")
	install_dependencies(tmpdir / plugin_id, tmpdir / "lib")
	return plugin_id


def install_plugin(source_dir: Path, name: str, system: bool = False) -> Path:
	"""Copy the prepared plugin from tmp to LIB_DIR"""
	plugin_dir = config.plugin_system_dir if system else config.plugin_user_dir
	if not plugin_dir.is_dir():
		raise FileNotFoundError(f"Plugin dir '{plugin_dir}' does not exist")

	if not name:
		raise ValueError("Attempting to install empty plugin.")
	logger.info("Installing libraries from '%s'", source_dir / "lib")
	shutil.rmtree(config.python_lib_dir / name, ignore_errors=True)
	shutil.copytree(source_dir / "lib", config.python_lib_dir / name)

	destination = plugin_dir / name
	logger.info("Installing plugin from '%s' to '%s'", source_dir / name, destination)
	if destination.exists():
		shutil.rmtree(destination)
	shutil.copytree(source_dir / name, destination)
	return destination


def install_python_package(target_dir: Path, package: dict[str, str]) -> None:
	# These imports take ~0.25s
	from pip._internal.commands.install import (
		InstallCommand,
	)
	from pip._vendor.distlib.scripts import (
		ScriptMaker,
	)

	def monkeypatched_make_multiple(
		self: ScriptMaker,
		specifications: list[str],
		options: dict[str, Any] | None = None,
	) -> list:
		return []

	# ScriptMaker is called by pip to create executable python scripts from libraries (i.e. .../bin)
	# Monkeypatch here to avoid trying to create this (nasty in frozen context)
	ScriptMaker.make_multiple = monkeypatched_make_multiple  # type: ignore

	target_dir.mkdir(parents=True, exist_ok=True)
	logger.info("Installing %r, version %r", package["name"], package["version"])
	# packaging version bundled in pip uses legacy format (see pip/__main__.py)
	with warnings.catch_warnings():
		warnings.filterwarnings("ignore", category=DeprecationWarning, module=".*packaging\\.version")
		try:
			install_args = [
				f"{package['name']}>={package['version']}",
				"--target",
				str(target_dir),
			]
			result = InstallCommand("install", "Install packages.").main(install_args)
			if result != 0:
				raise RuntimeError("Failed to install dependencies (pip call).")
		except Exception as error:
			logger.error("Could not install %r, aborting: %s", package["name"], error, exc_info=True)
			raise RuntimeError(f"Could not install {package['name']!r}, aborting") from error
		finally:
			config.set_logging_config()  # pip messes up logging config


def install_dependencies(path: Path, target_dir: Path) -> None:
	# Import is slow (python requests/urllib3)
	# pylint: disable=import-outside-toplevel

	from pip._vendor.distlib import resources
	from pipreqs import pipreqs  # type: ignore[import]

	logger.debug("Finder registry: %s", resources._finder_registry)

	try:
		import _frozen_importlib_external

		import pyimod02_importers

		resources._finder_registry[pyimod02_importers.PyiFrozenImporter] = resources._finder_registry[
			_frozen_importlib_external.SourceFileLoader
		]
		logger.debug("Finder registry: %s", resources._finder_registry)
	except ModuleNotFoundError as err:
		logger.debug(err)

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
			logger.trace("found present %s, version %s", dependency["name"], temp_module.__version__)
			assert parse(temp_module.__version__) >= parse(dependency["version"])
			logger.debug(
				"Module %r present in version %s (required %s) - not installing",
				dependency["name"],
				temp_module.__version__,
				dependency["version"],
			)
		except (ImportError, AssertionError, AttributeError, ModuleNotFoundError):
			install_python_package(target_dir, dependency)
	# Place requirements.txt at lib dir for possible later use (upgrade dependencies etc.)
	shutil.copy(path / "requirements.txt", target_dir)
