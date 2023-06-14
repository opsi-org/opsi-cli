"""
test_repository
"""

import shutil
from pathlib import Path

from .utils import run_cli

TEST_REPO = Path() / "tests" / "test_data" / "repository"


def test_repository_collect(tmp_path: Path) -> None:
	shutil.copytree(TEST_REPO, tmp_path / "data")
	returncode, _ = run_cli(["-l6", "repository", "create-meta-file", f"--meta-file={tmp_path / 'packages.json'}", str(tmp_path / "data")])
	assert returncode == 0
	result = (tmp_path / "packages.json").read_text()
	assert '"name": "opsi package repository"' in result
	assert '"schema_version": "1.1"' in result
	assert '"42.0-1337":' in result
	assert '"url": "data/localboot_new_42.0-1337.opsi"' in result
	assert '"1.0-1":' in result
	assert '"url": "data/localboot_new_1.0-1.opsi"' in result


def test_repository_update(tmp_path: Path) -> None:
	# check if update can create a file if not present
	(tmp_path / "data").mkdir()
	shutil.copy(TEST_REPO / "localboot_new_42.0-1337.opsi", tmp_path / "data")
	shutil.copy(TEST_REPO / "localboot_new_1.0-1.opsi", tmp_path / "data")
	returncode, _ = run_cli(
		[
			"-l6",
			"repository",
			"update-meta-file",
			f"--meta-file={tmp_path / 'packages.json'}",
			str(tmp_path / "data" / "localboot_new_42.0-1337.opsi"),
		]
	)
	assert returncode == 0
	result = (tmp_path / "packages.json").read_text()
	assert '"url": "data/localboot_new_42.0-1337.opsi"' in result

	# check if update adds new package and deletes other entries for same package
	returncode, _ = run_cli(
		[
			"-l6",
			"repository",
			"update-meta-file",
			f"--meta-file={tmp_path / 'packages.json'}",
			str(tmp_path / "data" / "localboot_new_1.0-1.opsi"),
		]
	)
	assert returncode == 0
	result = (tmp_path / "packages.json").read_text()
	assert '"url": "data/localboot_new_1.0-1.opsi"' in result
	assert '"url": "data/localboot_new_42.0-1337.opsi"' not in result

	# check if update adds new package and keeps others with --num-allowed-versions
	returncode, _ = run_cli(
		[
			"-l6",
			"repository",
			"update-meta-file",
			f"--meta-file={tmp_path / 'packages.json'}",
			str(tmp_path / "data" / "localboot_new_42.0-1337.opsi"),
			"--num-allowed-versions=2",
		]
	)
	assert returncode == 0
	result = (tmp_path / "packages.json").read_text()
	assert '"url": "data/localboot_new_42.0-1337.opsi"' in result
	assert '"url": "data/localboot_new_1.0-1.opsi"' in result


def test_repository_update_options(tmp_path: Path) -> None:
	returncode, _ = run_cli(
		[
			"-l6",
			"repository",
			"update-meta-file",
			f"--meta-file={tmp_path / 'packages.json'}",
			f"--relative-path={(tmp_path / 'nonexisting' / 'localboot_new_42.0-1337.opsi').relative_to(tmp_path)}",
			"--compatibility=linux,macos",
			str(TEST_REPO / "localboot_new_42.0-1337.opsi"),
		]
	)
	assert returncode == 0
	result = (tmp_path / "packages.json").read_text()
	assert '"url": "nonexisting/localboot_new_42.0-1337.opsi"' in result
	assert '"compatibility": ["linux", "macos"]' in result


def test_repository_update_multiple(tmp_path: Path) -> None:
	# check if update can create a file if not present
	(tmp_path / "data").mkdir()
	shutil.copy(TEST_REPO / "localboot_new_1.0-1.opsi", tmp_path / "data")
	shutil.copy(TEST_REPO / "localboot_new_2.0-1.opsi", tmp_path / "data")
	shutil.copy(TEST_REPO / "localboot_new_42.0-1337.opsi", tmp_path / "data")

	for package in ("localboot_new_1.0-1.opsi", "localboot_new_2.0-1.opsi", "localboot_new_42.0-1337.opsi"):
		call = [
			"-l6",
			"repository",
			"update-meta-file",
			f"--meta-file={tmp_path / 'packages.json'}",
			str(tmp_path / "data" / package),
			"--num-allowed-versions=2",
		]
		returncode, _ = run_cli(call)
		assert returncode == 0
	result = (tmp_path / "packages.json").read_text()
	assert '"url": "data/localboot_new_42.0-1337.opsi"' in result
	assert '"url": "data/localboot_new_2.0-1.opsi"' in result
	assert '"url": "data/localboot_new_1.0-1.opsi"' not in result
