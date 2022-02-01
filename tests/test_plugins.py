"""
opsi-cli Basic command line interface for opsi

Tests
"""

import os
from pathlib import Path
import pytest

from opsicli.plugin import install_python_package

from .utils import run_cli, temp_context

TESTPLUGIN = Path("tests") / "test_data" / "plugins" / "dummy"
FAULTYPLUGIN = Path("tests") / "test_data" / "plugins" / "faulty"
MISSINGPLUGIN = Path("tests") / "test_data" / "plugins" / "missing"


def test_pip() -> None:
	package = {"name": "netifaces", "version": "0.11.0"}
	with temp_context() as tempdir:
		install_python_package(tempdir, package)
		assert os.listdir(tempdir) and "netifaces" in os.listdir(tempdir)[0]


def test_initial() -> None:
	with temp_context():
		for args in [[], ["--help"], ["plugin"], ["plugin", "--help"], ["plugin", "add", "--help"], ["--version"], ["plugin", "--version"]]:
			assert run_cli(args)


def test_plugin_add() -> None:
	with temp_context():
		run_cli(["plugin", "add", str(TESTPLUGIN)])
		result = run_cli(["dummy", "libtest"])
		assert "Response" in result  # requests.get("https://opsi.org")
		assert "default" in result  # netifaces.gateways()


def test_plugin_add_fail() -> None:
	with temp_context():
		with pytest.raises(ValueError):
			run_cli(["plugin", "add", str(FAULTYPLUGIN)])
		# click checks command line argument path for existence and raises assertion error if missing
		with pytest.raises(AssertionError):
			run_cli(["plugin", "add", str(MISSINGPLUGIN)])


def test_plugin_remove() -> None:
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
