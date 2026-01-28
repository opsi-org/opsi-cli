# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_plugins
"""

import os
from pathlib import Path

from opsicli.config import config
from opsicli.plugin import PLUGIN_EXTENSION, install_python_package

from .utils import run_cli, temp_context

TESTPLUGIN = Path("tests") / "test_data" / "plugins" / "dummy"
FAULTYPLUGIN = Path("tests") / "test_data" / "plugins" / "faulty"
MISSINGPLUGIN = Path("tests") / "test_data" / "plugins" / "missing"


def test_initial() -> None:
	with temp_context():
		for args in [["--help"], ["plugin"], ["plugin", "--help"], ["plugin", "add", "--help"], ["--version"], ["plugin", "--version"]]:
			assert run_cli(args)


def test_install() -> None:
	package = {"name": "requests", "version": "2.32.3"}
	with temp_context() as tempdir:
		install_python_package(tempdir, package)
		assert os.listdir(tempdir) and "requests" in os.listdir(tempdir)


def test_plugin_add() -> None:
	with temp_context():
		exit_code, stdout, _stderr = run_cli(["plugin", "add", str(TESTPLUGIN)])
		assert exit_code == 0
		exit_code, stdout, _stderr = run_cli(["dummy", "libtest"])
		assert exit_code == 0
		assert "Response" in stdout  # requests.get("https://opsi.org")


def test_plugin_fail() -> None:
	with temp_context():
		exit_code, _stdout, stderr = run_cli(["plugin", "add", str(FAULTYPLUGIN)])
		assert exit_code == 1
		assert "Invalid path given" in stderr

		exit_code, _stdout, stderr = run_cli(["plugin", "add", str(MISSINGPLUGIN)])
		assert exit_code == 2
		assert "does not exist" in stderr

		run_cli(["plugin", "add", str(TESTPLUGIN)])
		exit_code, _stdout, _stderr = run_cli(["dummy", "libtest"])
		assert exit_code == 0

		# Break dummy plugin
		(config.plugin_user_dir / "dummy" / "python" / "__init__.py").unlink()
		exit_code, _stdout, stderr = run_cli(["dummy", "libtest"])
		print(stderr)
		assert exit_code == 1
		assert "Invalid command" in stderr


def test_plugin_remove() -> None:
	with temp_context():
		run_cli(["plugin", "add", str(TESTPLUGIN)])
		exit_code, stdout, _stderr = run_cli(["plugin", "list"])
		assert exit_code == 0
		assert "dummy" in stdout
		run_cli(["plugin", "remove", "dummy"])
		exit_code, stdout, _stderr = run_cli(["plugin", "list"])
		assert exit_code == 0
		assert "dummy" not in stdout


def test_pluginarchive_export_import(tmp_path: Path) -> None:
	with temp_context():
		destination = tmp_path / f"dummy.{PLUGIN_EXTENSION}"

		exit_code, _stdout, stderr = run_cli(["plugin", "add", str(TESTPLUGIN)])
		assert exit_code == 0
		assert "'dummy' installed" in stderr

		exit_code, _stdout, stderr = run_cli(["plugin", "export", "dummy", str(tmp_path)])
		assert exit_code == 0
		assert "'dummy' exported to" in stderr

		assert destination.exists()

		exit_code, _stdout, stderr = run_cli(["plugin", "remove", "dummy"])
		assert exit_code == 0
		assert "'dummy' removed" in stderr

		exit_code, _stdout, stderr = run_cli(["plugin", "add", str(destination)])
		assert exit_code == 0
		assert "'dummy' installed" in stderr

		exit_code, stdout, _stderr = run_cli(["plugin", "list"])
		assert exit_code == 0
		assert "dummy" in stdout


def test_plugin_new(tmp_path: Path) -> None:
	with temp_context():
		destination = tmp_path / "new_plugin_1"

		args = ["plugin", "new", "--description", "", "--version", "1.2.3", "--path", str(tmp_path), "New Plugin_1"]
		print(f"Calling opsicli with: {args}")
		exit_code, _stdout, stderr = run_cli(args)
		print(stderr)
		assert exit_code == 0
		assert "Plugin 'new-plugin-1' created" in stderr
		assert (destination / "python" / "__init__.py").exists()

		init_code = (destination / "python" / "__init__.py").read_text("utf-8")
		assert 'name: str = "New Plugin_1"' in init_code
		assert '__version__ = "1.2.3"' in init_code

		exit_code, _stdout, stderr = run_cli(["-l", "4", "plugin", "add", str(destination)])
		assert exit_code == 0
		assert "Plugin 'new-plugin-1' installed" in stderr

		exit_code, stdout, _stderr = run_cli(["-l", "4", "plugin", "list"])
		assert exit_code == 0
		assert "new-plugin-1" in stdout

		exit_code, _stdout, stderr = run_cli(["-l", "4", "plugin", "compress", str(destination), str(tmp_path)])
		assert exit_code == 0
		plugin_archive = tmp_path / "new-plugin-1.opsicliplug"
		assert f"Plugin source '{destination}' compressed to '{plugin_archive}'" in stderr
		assert plugin_archive.exists()

		exit_code, _stdout, stderr = run_cli(["-l", "4", "plugin", "add", str(plugin_archive)])
		assert exit_code == 0
		assert "Plugin 'new-plugin-1' installed" in stderr


def test_pluginarchive_extract_compress(tmp_path: Path) -> None:
	with temp_context():
		exit_code, _stdout, stderr = run_cli(["plugin", "compress", str(TESTPLUGIN), str(tmp_path)])
		assert exit_code == 0
		assert "compressed" in stderr
		assert (tmp_path / "dummy.opsicliplug").exists()

		exit_code, _stdout, stderr = run_cli(["plugin", "extract", str(tmp_path / "dummy.opsicliplug"), str(tmp_path)])
		assert exit_code == 0
		assert "extracted" in stderr
		assert (tmp_path / "dummy").is_dir()
		assert (tmp_path / "dummy" / "python" / "__init__.py").read_text("utf-8") == (TESTPLUGIN / "python" / "__init__.py").read_text(
			"utf-8"
		)


def test_flag_protected(tmp_path: Path) -> None:
	with temp_context():
		run_cli(["plugin", "new", "--description", "", "--version", "0.1.0", "--path", str(tmp_path), "config"])

		exit_code, _stdout, stderr = run_cli(["plugin", "add", str(tmp_path / "config")])
		print(stderr)
		assert exit_code == 0  # plugin is not added, exitcode is still 0 (could be used for many plugins at once)
		assert "Plugin 'config' installed into" not in stderr

		exit_code, _stdout, stderr = run_cli(["plugin", "remove", "config"])
		assert exit_code == 1  # not allowed to remove "config" as it is a protected plugin


def test_run_unavailable_plugin() -> None:
	with temp_context():
		exit_code, _stdout, stderr = run_cli(["invalid-plugin", "somecommand"])
		assert exit_code == 1
		assert "Error: Plugin 'invalid-plugin' not found." in stderr
