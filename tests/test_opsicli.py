import sys
from typing import Tuple
import pytest

from opsicli.__main__ import main

class Utils:
	#https://medium.com/python-pandemonium/testing-sys-exit-with-pytest-10c6e5f7726f
	@staticmethod
	def call_cli():
		with pytest.raises(SystemExit) as wrapped_e:
			main()				# pylint: disable=no-value-for-parameter
		assert wrapped_e.type == SystemExit
		assert str(wrapped_e).endswith("0")

	@staticmethod
	def set_args(args : Tuple):
		sys.argv = [sys.argv[0]]
		print(args)
		sys.argv.extend([part for part in args])

@pytest.fixture
def utils():
	return Utils

@pytest.mark.xfail(reason="does not work on windows since pip install fails")
def test_plugin_add(utils):
	utils.set_args(["plugin", "add", "commands/dummy"])
	utils.call_cli()

@pytest.mark.xfail(reason="click.get_current_context().obj is None if executed in pytest")
def test_plugin_export(utils):
	utils.set_args(["plugin", "export", "dummy"])
	utils.call_cli()

def test_initial(utils):
	for args in [[], ["support"], ["support", "collect"]]:
		utils.set_args(args)
		utils.call_cli()

def test_help(utils):
	for args in [["--help"], ["support", "--help"], ["support", "collect", "--help"]]:
		utils.set_args(args)
		utils.call_cli()

def test_version(utils):
	# support ticket does not have version
	for args in [["--version"], ["support", "--version"]]:
		utils.set_args(args)
		utils.call_cli()
