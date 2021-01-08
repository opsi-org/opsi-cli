import sys
import os
import pytest

from opsicli import cli, plugin_folder

class Utils:
	#https://medium.com/python-pandemonium/testing-sys-exit-with-pytest-10c6e5f7726f
	def call_cli():
		with pytest.raises(SystemExit) as wrapped_e:
			cli()
		assert wrapped_e.type == SystemExit
		assert str(wrapped_e).endswith("0")

	def set_args(args):
		sys.argv = [sys.argv[0]]
		print(args)
		sys.argv.extend([part for part in args])

@pytest.fixture
def utils():
	return Utils


def test_initial(utils):
	for args in [[], ["support"], ["support", "ticket"]]:
		utils.set_args(args)
		utils.call_cli()

def test_help(utils):
	for args in [["--help"], ["support", "--help"], ["support", "ticket", "--help"]]:
		utils.set_args(args)
		utils.call_cli()

def test_version(utils):
	# support ticket does not have version
	for args in [["--version"], ["support", "--version"]]:
		utils.set_args(args)
		utils.call_cli()

def test_subcommands(utils):
	commands = []
	for filename in os.listdir(plugin_folder):
		if filename.endswith('.py'):
			commands.append(filename[:-3])
	for command in commands:
		utils.set_args([command])
		utils.call_cli()
