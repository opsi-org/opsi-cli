"""
opsi-cli Basic command line interface for opsi

Tests
"""

import os
from click.testing import CliRunner

from opsicli.__main__ import main

runner = CliRunner()


def test_initial():
	for args in [[], ["plugin"], ["--help"], ["plugin", "--help"], ["plugin", "export", "--help"], ["--version"], ["plugin", "--version"]]:
		result = runner.invoke(main, args, obj={})
		assert result.exit_code == 0


# @pytest.mark.xfail(reason="does not work on windows since pip install fails")
def test_plugin_add_remove():
	result = runner.invoke(main, ["plugin", "add", "commands/dummy"], obj={})
	assert result.exit_code == 0
	result = runner.invoke(main, ["plugin", "list"], obj={})
	assert result.exit_code == 0
	assert "dummy" in result.output
	result = runner.invoke(main, ["plugin", "remove", "dummy"], obj={})
	assert result.exit_code == 0
	result = runner.invoke(main, ["plugin", "list"], obj={})
	assert result.exit_code == 0
	assert "dummy" not in result.output


def test_pluginarchive_export_import():
	result = runner.invoke(main, ["plugin", "add", "commands/dummy"], obj={})
	assert result.exit_code == 0
	result = runner.invoke(main, ["plugin", "export", "dummy"], obj={})
	assert result.exit_code == 0
	os.path.exists("dummy.opsiplugin")
	result = runner.invoke(main, ["plugin", "remove", "dummy"], obj={})
	assert result.exit_code == 0
	result = runner.invoke(main, ["plugin", "add", "dummy.opsiplugin"], obj={})
	assert result.exit_code == 0
	result = runner.invoke(main, ["plugin", "list"], obj={})
	assert result.exit_code == 0
	assert "dummy" in result.output
