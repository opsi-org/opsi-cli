"""
test_self
"""

from pathlib import Path

from .utils import run_cli, temp_context


def test_self_install() -> None:
	with temp_context() as tempdir:
		outfile = Path(tempdir) / "out_binary"
		(exit_code, _) = run_cli(["self", "install", f"--binary-path={outfile}", "--ignore-environment"])
		assert exit_code == 0
		assert outfile.exists()
