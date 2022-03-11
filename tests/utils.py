"""
opsi-cli Basic command line interface for opsi

Test utilities
"""

import os
from contextlib import contextmanager
import tempfile
from pathlib import Path
from typing import Sequence, Generator, Tuple
from click.testing import CliRunner

from opsicli.__main__ import main
from opsicli.config import config

runner = CliRunner()


def run_cli(args: Sequence[str]) -> Tuple[int, str]:
	result = runner.invoke(main, args, obj={}, catch_exceptions=False)
	return (result.exit_code, result.output)


@contextmanager
def temp_context() -> Generator[Path, None, None]:
	values = config.get_values()
	try:
		with tempfile.TemporaryDirectory() as tempdir:
			tempdir_path = Path(tempdir)
			config.color = False
			config.lib_dir = tempdir_path / "lib"
			plugin_dirs = config.plugin_dirs
			plugin_dirs[-1] = tempdir_path / "plugin"
			config.plugin_dirs = plugin_dirs
			yield tempdir_path
	finally:
		config.set_values(values)


@contextmanager
def temp_env(**environ):
	old_environ = dict(os.environ)
	os.environ.update(environ)
	try:
		yield
	finally:
		os.environ.clear()
		os.environ.update(old_environ)
