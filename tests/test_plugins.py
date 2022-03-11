"""
test_plugins
"""

import os
import platform
from pathlib import Path
import pytest

from opsicli.plugin import PLUGIN_EXTENSION, install_python_package, plugin_manager
from opsicli.config import config

from .utils import run_cli, temp_context, temp_env

TESTPLUGIN = Path("tests") / "test_data" / "plugins" / "dummy"
FAULTYPLUGIN = Path("tests") / "test_data" / "plugins" / "faulty"
MISSINGPLUGIN = Path("tests") / "test_data" / "plugins" / "missing"


def test_initial() -> None:
	with temp_context():
		for args in [["--help"], ["plugin"], ["plugin", "--help"], ["plugin", "add", "--help"], ["--version"], ["plugin", "--version"]]:
			assert run_cli(args)


def test_no_python_path() -> None:
	with temp_context():
		with temp_env(PATH=""):
			# no python found in PATH (check this before any plugin add since lru_cache otherwise uses cached value)
			(exit_code, output) = run_cli(["plugin", "add", str(TESTPLUGIN)])
			assert exit_code == 1
			assert "Could not find python path" in output


def test_pip() -> None:
	package = {"name": "netifaces", "version": "0.11.0"}
	with temp_context() as tempdir:
		install_python_package(tempdir, package)
		assert os.listdir(tempdir) and "netifaces" in os.listdir(tempdir)[0]


# Permission Error on windows: file unlink is impossible if handle is opened
# Problem: add plugin, then load plugin -> open file handle until teardown of python process
@pytest.mark.skipif(platform.system().lower() == "windows", reason="Must not run under windows")
def test_plugin_add() -> None:
	with temp_context():
		run_cli(["plugin", "add", str(TESTPLUGIN)])
		_exit_code, result = run_cli(["dummy", "libtest"])
		assert "Response" in result  # requests.get("https://opsi.org")
		assert "default" in result  # netifaces.gateways()


def test_plugin_fail() -> None:
	with temp_context():
		exit_code, output = run_cli(["plugin", "add", str(FAULTYPLUGIN)])
		assert exit_code == 1
		assert "Invalid path given" in output

		exit_code, output = run_cli(["plugin", "add", str(MISSINGPLUGIN)])
		assert exit_code == 2
		assert "does not exist" in output

		run_cli(["plugin", "add", str(TESTPLUGIN)])
		exit_code, output = run_cli(["dummy", "libtest"])
		assert exit_code == 0

		plugin_manager.unload_plugins()

		# Break dummy plugin
		(config.plugin_dirs[-1] / "dummy" / "python" / "__init__.py").unlink()
		exit_code, output = run_cli(["dummy", "libtest"])
		assert exit_code == 1
		assert "Invalid command" in output


# Permission Error on windows: file unlink is impossible if handle is opened
# Problem: add plugin, then load plugin -> open file handle until teardown of python process
@pytest.mark.skipif(platform.system().lower() == "windows", reason="Must not run under windows")
def test_plugin_remove() -> None:
	with temp_context():
		run_cli(["plugin", "add", str(TESTPLUGIN)])
		exit_code, output = run_cli(["plugin", "list"])
		assert exit_code == 0
		assert "dummy" in output
		run_cli(["plugin", "remove", "dummy"])
		exit_code, output = run_cli(["plugin", "list"])
		assert exit_code == 0
		assert "dummy" not in output


# Permission Error on windows: file unlink is impossible if handle is opened
# Problem: add plugin, then load plugin -> open file handle until teardown of python process
@pytest.mark.skipif(platform.system().lower() == "windows", reason="Must not run under windows")
def test_pluginarchive_export_import(tmp_path) -> None:
	with temp_context():
		destination = tmp_path / f"dummy.{PLUGIN_EXTENSION}"

		exit_code, output = run_cli(["plugin", "add", str(TESTPLUGIN)])
		assert exit_code == 0
		assert "Plugin 'dummy' installed" in output

		exit_code, output = run_cli(["plugin", "export", "dummy", str(tmp_path)])
		assert exit_code == 0
		assert "Plugin 'dummy' exported to" in output

		assert destination.exists()

		exit_code, output = run_cli(["plugin", "remove", "dummy"])
		assert exit_code == 0
		assert "Plugin 'dummy' removed" in output

		exit_code, output = run_cli(["plugin", "add", str(destination)])
		assert exit_code == 0
		assert "Plugin 'dummy' installed" in output

		exit_code, output = run_cli(["plugin", "list"])
		assert exit_code == 0
		assert "dummy" in output
