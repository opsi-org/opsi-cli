"""
test_repository
"""

from pathlib import Path

from .utils import run_cli

TEST_REPO = Path() / "tests" / "test_data" / "repository"


def test_repository_collect(tmp_path: Path) -> None:
	returncode, _ = run_cli(["-l6", "repository", "create-meta-file", f"--output-file={tmp_path / 'packages.json'}", str(TEST_REPO)])
	assert returncode == 0
	result = (tmp_path / "packages.json").read_text()
	print(result)
	assert '"schema_version": "1.1"' in result
	assert '"name": "testrepo"' in result
	assert '"localboot_new;42.0;1337":' in result
	assert '"url": "tests/test_data/repository/localboot_new_42.0-1337.opsi"' in result
