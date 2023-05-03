"""
test_repository
"""

from pathlib import Path

from .utils import run_cli

TEST_REPO = Path() / "tests" / "test_data" / "repository"


def test_repository_collect(tmp_path: Path) -> None:
	returncode, _ = run_cli(["-l6", "repository", "create-meta-file", f"--meta-file={tmp_path / 'packages.json'}", str(TEST_REPO)])
	assert returncode == 0
	result = (tmp_path / "packages.json").read_text()
	assert '"name": "opsi package repository"' in result
	assert '"schema_version": "1.1"' in result
	assert '"42.0-1337":' in result
	assert '"url": "tests/test_data/repository/localboot_new_42.0-1337.opsi"' in result
	assert '"1.0-1":' in result
	assert '"url": "tests/test_data/repository/localboot_new_1.0-1.opsi"' in result


def test_repository_update(tmp_path: Path) -> None:
	# check if update can create a file if not present
	returncode, _ = run_cli(
		[
			"-l6",
			"repository",
			"update-meta-file",
			f"--meta-file={tmp_path / 'packages.json'}",
			str(TEST_REPO / "localboot_new_42.0-1337.opsi"),
		]
	)
	assert returncode == 0
	result = (tmp_path / "packages.json").read_text()
	assert '"url": "tests/test_data/repository/localboot_new_42.0-1337.opsi"' in result

	# check if update adds new package and deletes other entries for same package
	returncode, _ = run_cli(
		[
			"-l6",
			"repository",
			"update-meta-file",
			f"--meta-file={tmp_path / 'packages.json'}",
			str(TEST_REPO / "localboot_new_1.0-1.opsi"),
		]
	)
	assert returncode == 0
	result = (tmp_path / "packages.json").read_text()
	assert '"url": "tests/test_data/repository/localboot_new_1.0-1.opsi"' in result
	assert '"url": "tests/test_data/repository/localboot_new_42.0-1337.opsi"' not in result

	# check if update adds new package and keeps others with --keep-other-versions
	returncode, _ = run_cli(
		[
			"-l6",
			"repository",
			"update-meta-file",
			f"--meta-file={tmp_path / 'packages.json'}",
			str(TEST_REPO / "localboot_new_42.0-1337.opsi"),
			"--keep-other-versions",
		]
	)
	assert returncode == 0
	result = (tmp_path / "packages.json").read_text()
	assert '"url": "tests/test_data/repository/localboot_new_42.0-1337.opsi"' in result
	assert '"url": "tests/test_data/repository/localboot_new_1.0-1.opsi"' in result
