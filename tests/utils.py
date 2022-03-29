"""
opsi-cli Basic command line interface for opsi

Test utilities
"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Sequence, Tuple

from click.testing import CliRunner

from opsicli.__main__ import main
from opsicli.config import config
from opsicli.plugin import plugin_manager

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
			config.python_lib_dir = tempdir_path / "lib"
			config.plugin_user_dir = tempdir_path / "user_plugins"
			config.plugin_system_dir = tempdir_path / "system_plugins"
			yield tempdir_path
	finally:
		plugin_manager.unload_plugins()
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
