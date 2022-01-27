"""
opsi-cli Basic command line interface for opsi

Test utilities
"""

from typing import Iterable
from click.testing import CliRunner

from opsicommon.logging import logger

from opsicli.__main__ import main

runner = CliRunner()


def run_cli(args: Iterable) -> str:
	result = runner.invoke(main, args, obj={})
	if result.exit_code:
		logger.error("cli call failed with args %s\noutput: %s", args, result.output)
	assert result.exit_code == 0
	return result.output
