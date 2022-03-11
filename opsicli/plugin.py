# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

plugin handling
"""
import os
import shutil
import zipfile
import subprocess
import importlib
from typing import Dict
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
from types import ModuleType

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
	destination = config.plugin_dir / name
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


class PluginManager(metaclass=Singleton):  # pylint: disable=too-few-public-methods
	def __init__(self) -> None:
		self.plugin_modules: Dict[str, ModuleType] = {}
		# prepare_context(ctx)

	def load_plugins(self) -> None:
		if self.plugin_modules:
			# Already loaded
			return

		for plugin_base_dir in config.plugin_dirs:
			if not plugin_base_dir.exists():
				continue
			logger.debug("Loading plugins from dir '%s'", plugin_base_dir)
			for plugin_dir in plugin_base_dir.iterdir():
				try:
					self.load_plugin(plugin_dir)
				except ImportError as import_error:
					logger.error("Could not load plugin from %r: %s", plugin_dir, import_error, exc_info=True)
					raise  # continue

	def load_plugin(self, plugin_dir: Path) -> None:
		logger.info("Loading plugin from '%s'", plugin_dir)
		path = plugin_dir / "__init__.py"
		if not path.exists():
			raise ImportError(f"{plugin_dir!r} does not have __init__.py")
		spec = spec_from_file_location("temp", path)
		if not spec:
			raise ImportError(f"{path!r} is not a valid python module")
		new_plugin = module_from_spec(spec)
		if not spec.loader:
			raise ImportError(f"{path!r} spec does not have valid loader")
		spec.loader.exec_module(new_plugin)
		# TODO: Validate plugin info structure
		try:
			name = new_plugin.get_plugin_info()["name"]
		except (AttributeError, KeyError) as error:
			raise ImportError(f"{plugin_dir!r} does not have a valid get_plugin_info method (key name required)") from error
		new_plugin.plugin_path = plugin_dir  # type: ignore[attr-defined]
		self.plugin_modules[name] = new_plugin

		logger.debug("Added plugin %r", name)

	def get_plugin_path(self, plugin_name: str) -> Path:
		if plugin_name not in self.plugin_modules:
			raise ValueError(f"Plugin {plugin_name!r} not found")
		return self.plugin_modules[plugin_name].plugin_dir


plugin_manager = PluginManager()
