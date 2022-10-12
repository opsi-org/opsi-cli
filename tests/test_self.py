"""
test_self
"""

from pathlib import Path

from opsicli.config import config

from .utils import run_cli, temp_context


def test_self_install() -> None:
	with temp_context() as tempdir:
		binary_path = Path(tempdir) / "out_binary"
		(exit_code, output) = run_cli(["self", "install", f"--binary-path={binary_path}", "--no-add-to-path"])
		print(output)
		assert exit_code == 0
		assert binary_path.exists()
		assert config.config_file_user.exists()


def test_self_uninstall() -> None:
	with temp_context() as tempdir:
		binary_path = Path(tempdir) / "out_binary"
		(exit_code, _) = run_cli(["self", "install", f"--binary-path={binary_path}", "--no-add-to-path"])
		(exit_code, output) = run_cli(["self", "uninstall", f"--binary-path={binary_path}"])
		print(output)
		assert exit_code == 0
		assert not binary_path.exists()
		assert not config.config_file_user.exists()
