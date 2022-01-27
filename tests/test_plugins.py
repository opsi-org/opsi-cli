"""
opsi-cli Basic command line interface for opsi

Tests
"""

import os
import shutil

from opsicli import CLI_BASE_PATH, LIB_DIR, make_cli_paths
from opsicli.plugin import install_python_package

from .utils import run_cli

TESTPLUGIN = os.path.join("tests", "test_data", "commands", "dummy")


def test_pip():
	shutil.rmtree(CLI_BASE_PATH, ignore_errors=True)
	make_cli_paths()
	package = {"name": "netifaces", "version": "0.11.0"}
	install_python_package(LIB_DIR, package)
	assert os.listdir(LIB_DIR) and "netifaces" in os.listdir(LIB_DIR)[0]


def test_initial():
	for args in [[], ["--help"], ["plugin"], ["plugin", "--help"], ["plugin", "add", "--help"], ["--version"], ["plugin", "--version"]]:
		assert run_cli(args)


def test_plugin_add_remove():
	shutil.rmtree(CLI_BASE_PATH, ignore_errors=True)
	run_cli(["plugin", "add", TESTPLUGIN])
	output = run_cli(["plugin", "list"])
	assert "dummy" in output
	run_cli(["plugin", "remove", "dummy"])
	output = run_cli(["plugin", "list"])
	assert "dummy" not in output


def test_pluginarchive_export_import():
	shutil.rmtree(CLI_BASE_PATH, ignore_errors=True)
	run_cli(["plugin", "add", TESTPLUGIN])
	run_cli(["plugin", "export", "dummy"])
	assert os.path.exists("dummy.opsiplugin")
	run_cli(["plugin", "remove", "dummy"])
	run_cli(["plugin", "add", "dummy.opsiplugin"])
	output = run_cli(["plugin", "list"])
	assert "dummy" in output
