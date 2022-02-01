"""
opsi-cli Basic command line interface for opsi

Test utilities
"""

from contextlib import contextmanager
import tempfile
from pathlib import Path
from typing import Iterable
from click.testing import CliRunner

from opsicommon.logging import logger

from opsicli.__main__ import main
from opsicli.config import config

runner = CliRunner()


def run_cli(args: Iterable) -> str:
	result = runner.invoke(main, args, obj={}, catch_exceptions=False)
	if result.exit_code:
		logger.error("cli call failed with args %s\noutput: %s", args, result.output)
	assert result.exit_code == 0
	return result.output


@contextmanager
def temp_context() -> Path:
	try:
		with tempfile.TemporaryDirectory() as tempdir:
			tempdir = Path(tempdir)
			config.set_value("cli_base_dir", tempdir)
			config.set_value("lib_dir", tempdir / "lib")
			config.set_value("plugin_dir", tempdir / "plugin")
			yield tempdir
	finally:
		config.set_defaults()
