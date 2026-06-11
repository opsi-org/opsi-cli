# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli Basic command line interface for opsi

plugin handling
"""

from __future__ import annotations

import importlib
import os
import re
import shutil
import sys
import warnings
import zipfile
from importlib._bootstrap import BuiltinImporter
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

import opsi
from click import Command
from opsi.logging import get_logger
from packaging.version import parse

from opsicli.config import COMPLETION_MODE, config

sys.modules["opsicommon"] = opsi

logger = get_logger("opsicli")

PLUGIN_EXTENSION = "opsicliplug"

PLUGIN_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_\- ]+$")
PLUGIN_ID_REGEX = re.compile(r"^[a-z0-9\-]+$")


def verify_plugin_name(plugin_name: str) -> str:
	if not re.match(PLUGIN_NAME_REGEX, plugin_name):
		raise ValueError(f"Invalid plugin name '{plugin_name}'. Only alphanumeric characters, spaces, hyphens and underscores are allowed.")
	return plugin_name


def verify_plugin_id(plugin_id: str) -> str:
	if not re.match(PLUGIN_ID_REGEX, plugin_id):
		raise ValueError(f"Invalid plugin id '{plugin_id}'. Only alphanumeric characters, hyphens and underscores are allowed.")
	return plugin_id


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
	def find_spec(cls, fullname: str, path: None = None, target: None = None) -> ModuleSpec | None:  # ty: ignore[invalid-method-override]
		if not fullname.startswith("opsicli.addon"):
			return None
		encoded = fullname.split("_", 1)[1]
		if "." in encoded:
			return None
		plugin_path = bytes.fromhex(encoded).decode("utf-8")
		init_path = os.path.join(plugin_path, "python", "__init__.py")
		logger.debug("Searching spec for %s", init_path)
		if not os.path.exists(init_path):
			return None
		return importlib.util.spec_from_file_location(fullname, init_path)  # ty: ignore[possibly-missing-submodule]


sys.meta_path.append(PluginImporter)  # ty: ignore[invalid-argument-type]


class PluginManager:
	_instance: PluginManager | None = None

	def __new__(cls) -> PluginManager:
		if cls._instance is None:
			cls._instance = super().__new__(cls)
		return cls._instance

	def __init__(self) -> None:
		if getattr(self, "_initialized", False):
			return
		self._initialized = True

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
				try:
					plugin_id = verify_plugin_id(plugin_dir.name.replace("_", "-"))
				except ValueError as err:
					logger.warning("Skipping invalid plugin dir '%s': %s", plugin_dir, err)
					continue
				if (plugin_dir / "python" / "__init__.py").exists() and plugin_id not in plugin_ids:
					plugin_ids.append(plugin_id)
		return plugin_ids

	def load_plugin_module(self, plugin_dir: Path) -> ModuleType:
		"""
		Directory structure:
		<base_dir>/
		├──	plugins/
		│   └──	plugin_id/
		└──	lib/
		    └──	plugin_id/
		"""
		associated_lib_dir = None
		if plugin_dir.is_relative_to(config.plugin_system_dir):
			associated_lib_dir = config.lib_system_dir / plugin_dir.name
		elif plugin_dir.is_relative_to(config.plugin_user_dir):
			associated_lib_dir = config.lib_user_dir / plugin_dir.name
		if associated_lib_dir and associated_lib_dir.exists() and str(associated_lib_dir) not in sys.path:
			logger.debug("Prepending to sys.path: %s", associated_lib_dir)
			sys.path.insert(0, str(associated_lib_dir))
		logger.debug("Extracting plugin object from '%s'", plugin_dir)
		logger.debug("sys.path = %s", sys.path)
		module_name = self.module_name(plugin_dir)
		for sys_module in list(sys.modules):
			if sys_module.startswith(module_name):
				del sys.modules[sys_module]
		return importlib.import_module(self.module_name(plugin_dir))

	def get_plugin_dir(self, name: str) -> Path:
		dir_name = name.replace("-", "_")
		for plugin_base_dir in (config.plugin_bundle_dir, config.plugin_system_dir, config.plugin_user_dir):
			if not plugin_base_dir:
				continue
			if not plugin_base_dir.exists():
				logger.debug("Plugin dir '%s' not found", plugin_base_dir)
				continue
			if (plugin_base_dir / dir_name).exists():
				logger.debug("Found plugin %r at '%s'", name, plugin_base_dir / dir_name)
				return plugin_base_dir / dir_name
		raise FileNotFoundError(f"Plugin '{name}' not found.")

	def get_plugin_lib_dir(self, name: str) -> Path:
		dir_name = name.replace("-", "_")
		for lib_base_dir in (config.lib_system_dir, config.lib_user_dir):
			if not lib_base_dir:
				continue
			if not lib_base_dir.exists():
				logger.debug("Plugin dependency dir '%s' not found", lib_base_dir)
				continue
			if (lib_base_dir / dir_name).exists():
				logger.debug("Found plugin dependency %r at '%s'", name, lib_base_dir / dir_name)
				return lib_base_dir / dir_name
		raise FileNotFoundError(f"Plugin dependencies for '{name}' not found.")

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
	plugin_id = verify_plugin_id(path.stem.replace("_", "-"))
	plugin_tmp_path = tmpdir / plugin_id.replace("-", "_")
	logger.info("Preparing plugin '%s' in '%s'", plugin_id, plugin_tmp_path)
	if (path / "python" / "__init__.py").exists():
		shutil.copytree(path, plugin_tmp_path)
	elif path.suffix == f".{PLUGIN_EXTENSION}":
		with zipfile.ZipFile(path, "r") as zfile:
			zfile.extractall(tmpdir)
	else:
		raise ValueError(f"Invalid path given '{path}'")

	logger.info("Retrieving libraries for new plugin")
	install_dependencies(plugin_tmp_path, tmpdir / "lib")
	return plugin_id


def set_plugin_permissions(path: Path) -> None:
	logger.info("setting rights for %s", path)
	if path.is_dir():
		path.chmod(0o775)
	else:
		path.chmod(0o664)
	# set rights 775 for path and all subdirs/files to allow usage by non-admin users on linux using pathlib iterdir
	for path in Path(path).iterdir():
		if path.is_dir():
			path.chmod(0o775)
		else:
			path.chmod(0o664)


def install_plugin(source_dir: Path, plugin_id: str, system: bool = False) -> Path:
	"""Copy the prepared plugin from tmp to LIB_DIR"""
	plugin_path_name = plugin_id.replace("-", "_")
	plugin_dir = config.plugin_system_dir if system else config.plugin_user_dir
	python_lib_dir = config.lib_user_dir / plugin_path_name if not system else config.lib_system_dir / plugin_path_name
	if not plugin_dir.is_dir():
		plugin_dir.mkdir(parents=True)

	if not plugin_id:
		raise ValueError("Attempting to install empty plugin.")

	logger.info("Installing libraries from '%s' to '%s'", source_dir / "lib", python_lib_dir)
	shutil.rmtree(python_lib_dir, ignore_errors=True)
	shutil.copytree(source_dir / "lib", python_lib_dir)
	set_plugin_permissions(python_lib_dir)

	destination = plugin_dir / plugin_path_name
	logger.info("Installing plugin from '%s' to '%s'", source_dir / plugin_path_name, destination)
	if destination.exists():
		shutil.rmtree(destination)
	shutil.copytree(source_dir / plugin_path_name, destination)
	set_plugin_permissions(destination)
	return destination


def install_python_package(target_dir: Path, package: dict[str, str]) -> None:
	# These imports take ~0.25s
	import pip._internal.commands.install
	from pip._internal.commands.install import InstallCommand
	from pip._vendor.distlib.scripts import ScriptMaker

	def monkeypatched_make_multiple(
		self: ScriptMaker,
		specifications: list[str],
		options: dict[str, Any] | None = None,
	) -> list:
		return []

	# Monkeypatch warn_if_run_as_root to ignore warnings, since we use custom package pool anyway
	pip._internal.commands.install.warn_if_run_as_root = lambda: None  # ty: ignore
	# ScriptMaker is called by pip to create executable python scripts from libraries (i.e. .../bin)
	# Monkeypatch here to avoid trying to create this (nasty in frozen context)
	ScriptMaker.make_multiple = monkeypatched_make_multiple  # ty: ignore

	target_dir.mkdir(parents=True, exist_ok=True)
	logger.info("Installing %r, version %r", package["name"], package["version"])
	# packaging version bundled in pip uses legacy format (see pip/__main__.py)
	with warnings.catch_warnings():
		warnings.filterwarnings("ignore", category=DeprecationWarning, module=".*packaging\\.version")
		try:
			install_args = [
				f"{package['name']}>={package['version']}" if package["version"] else package["name"],
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

	from pip._vendor.distlib import resources
	from pipreqs import pipreqs

	logger.debug("Finder registry: %s", resources._finder_registry)

	try:
		import _frozen_importlib_external

		try:
			import pyimod02_importers  # ty: ignore[unresolved-import]
		except ImportError:
			from PyInstaller.loader import pyimod02_importers

		resources._finder_registry[pyimod02_importers.PyiFrozenLoader] = resources._finder_registry[  # ty: ignore
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
		# this failes for packages not available at pypi.python.org (like opsi) -> those are ignored	TODO
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
