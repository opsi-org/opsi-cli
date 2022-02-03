"""
opsi-cli Basic command line interface for opsi

Test utilities
"""

import os
from contextlib import contextmanager
import tempfile
from pathlib import Path
from typing import Sequence, Generator
from click.testing import CliRunner

from opsicommon.logging import logger

from opsicli.__main__ import main
from opsicli.config import config

runner = CliRunner()


def run_cli(args: Sequence[str]) -> str:
	result = runner.invoke(main, args, obj={}, catch_exceptions=False)
	if result.exit_code:
		logger.error("cli call failed with args %s\noutput: %s", args, result.output)
	assert result.exit_code == 0
	return result.output


@contextmanager
def temp_context() -> Generator[Path, None, None]:
	try:
		with tempfile.TemporaryDirectory() as tempdir:
			tempdir_path = Path(tempdir)
			config.set_value("cli_base_dir", tempdir_path)
			config.set_value("lib_dir", tempdir_path / "lib")
			config.set_value("plugin_dir", tempdir_path / "plugin")
			yield tempdir_path
	finally:
		config.set_defaults()


@contextmanager
def temp_env(**environ):
	old_environ = dict(os.environ)
	os.environ.update(environ)
	try:
		yield
	finally:
		os.environ.clear()
		os.environ.update(old_environ)
