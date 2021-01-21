import sys
from typing import Tuple
import pytest

from opsicli.__main__ import cli

class Utils:
	#https://medium.com/python-pandemonium/testing-sys-exit-with-pytest-10c6e5f7726f
	@staticmethod
	def call_cli():
		with pytest.raises(SystemExit) as wrapped_e:
			cli()
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
