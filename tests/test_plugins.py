"""
opsi-cli Basic command line interface for opsi

Tests
"""

import os
import platform
from pathlib import Path
import pytest

from opsicli.plugin import install_python_package
from opsicli.config import config

from .utils import run_cli, temp_context, temp_env

TESTPLUGIN = Path("tests") / "test_data" / "plugins" / "dummy"
FAULTYPLUGIN = Path("tests") / "test_data" / "plugins" / "faulty"
MISSINGPLUGIN = Path("tests") / "test_data" / "plugins" / "missing"


def test_initial() -> None:
	with temp_context():
		for args in [[], ["--help"], ["plugin"], ["plugin", "--help"], ["plugin", "add", "--help"], ["--version"], ["plugin", "--version"]]:
			assert run_cli(args)


def test_no_python_path() -> None:
	with temp_context():
		with temp_env(PATH=""):
			# no python found in PATH (check this before any plugin add since lru_cache otherwise uses cached value)
			with pytest.raises(RuntimeError):
				run_cli(["plugin", "add", str(TESTPLUGIN)])


def test_pip() -> None:
	package = {"name": "netifaces", "version": "0.11.0"}
	with temp_context() as tempdir:
		install_python_package(tempdir, package)
		assert os.listdir(tempdir) and "netifaces" in os.listdir(tempdir)[0]


def test_plugin_add() -> None:
	# Permission Error on windows: file unlink is impossible if handle is opened
	# Problem: add plugin, then load plugin -> open file handle until teardown of python process
	if platform.system().lower() == "windows":
		pytest.skip("Must not run under windows")

	with temp_context():
		run_cli(["plugin", "add", str(TESTPLUGIN)])
		result = run_cli(["dummy", "libtest"])
		assert "Response" in result  # requests.get("https://opsi.org")
		assert "default" in result  # netifaces.gateways()


def test_plugin_fail() -> None:
	with temp_context():
		with pytest.raises(ValueError):
			run_cli(["plugin", "add", str(FAULTYPLUGIN)])

		# click checks command line argument path for existence and raises assertion error if missing
		with pytest.raises(AssertionError):
			run_cli(["plugin", "add", str(MISSINGPLUGIN)])

		run_cli(["plugin", "add", str(TESTPLUGIN)])
		# break dummy plugin
		os.remove(config.plugin_dir / "dummy" / "__init__.py")
		with pytest.raises(ImportError):
			run_cli(["plugin", "list"])


def test_plugin_remove() -> None:
	# Permission Error on windows: file unlink is impossible if handle is opened
	# Problem: add plugin, then load plugin -> open file handle until teardown of python process
	if platform.system().lower() == "windows":
		pytest.skip("Must not run under windows")

	with temp_context():
		run_cli(["plugin", "add", str(TESTPLUGIN)])
		output = run_cli(["plugin", "list"])
		assert "dummy" in output
		run_cli(["plugin", "remove", "dummy"])
		output = run_cli(["plugin", "list"])
		assert "dummy" not in output


def test_pluginarchive_export_import() -> None:
	with temp_context():
		run_cli(["plugin", "add", str(TESTPLUGIN)])
		run_cli(["plugin", "export", "dummy"])
		assert os.path.exists("dummy.opsiplugin")
		run_cli(["plugin", "remove", "dummy"])
		run_cli(["plugin", "add", "dummy.opsiplugin"])
		output = run_cli(["plugin", "list"])
		assert "dummy" in output
