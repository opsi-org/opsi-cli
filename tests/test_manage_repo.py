"""
test_repository
"""

import shutil
from pathlib import Path

import zstandard
from msgspec import json, msgpack

from .utils import run_cli

TEST_REPO = Path() / "tests" / "test_data" / "repository"


def read_metafile(file: Path) -> dict:
	bdata = file.read_bytes()
	if ".zstd" in file.suffixes:
		decompressor = zstandard.ZstdDecompressor()
		bdata = decompressor.decompress(bdata)
	data = msgpack.decode(bdata) if ".msgpack" in file.suffixes else json.decode(bdata)
	return data


def test_metafile_create(tmp_path: Path) -> None:
	repository_dir = tmp_path / "repository-dir"
	formats = ["json", "msgpack", "msgpack.zstd"]

	shutil.copytree(TEST_REPO, repository_dir)

	cmd = ["-l6", "manage-repo", "metafile", "create", str(repository_dir), "--scan"] + [f"--format={f}" for f in formats]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	for suffix in formats:
		data = read_metafile(repository_dir / f"packages.{suffix}")
		assert data["repository"]["name"] == "opsi package repository"
		assert data["schema_version"] == "1.1"
		assert data["packages"]["localboot_new"]["42.0-1337"]["url"] == "localboot_new_42.0-1337.opsi"
		assert data["packages"]["localboot_new"]["1.0-1"]["url"] == "localboot_new_1.0-1.opsi"
		assert data["packages"]["test-netboot"]["1.0-2"]["url"] == "subdir/test-netboot_1.0-2.opsi"

	# Recreate without scanning, other name and formats
	cmd = ["-l6", "manage-repo", "metafile", "create", str(repository_dir), "--format=json", "--repository-name=myrepo"]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	for suffix in formats:
		metafile = repository_dir / f"packages.{suffix}"
		if suffix == "json":
			data = read_metafile(metafile)
			assert data["repository"]["name"] == "myrepo"
			assert data["schema_version"] == "1.1"
			assert not data["packages"]
		else:
			assert not metafile.exists()


def test_metafile_update(tmp_path: Path) -> None:
	repository_dir = tmp_path / "repository-dir"
	formats = ["json", "msgpack", "msgpack.zstd"]

	shutil.copytree(TEST_REPO, repository_dir)

	# Update must create metafiles if they do not exist
	cmd = ["-l6", "manage-repo", "metafile", "update", str(repository_dir), "--repository-name=myrepo", "--scan"] + [
		f"--format={f}" for f in formats
	]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	for suffix in formats:
		data = read_metafile(repository_dir / f"packages.{suffix}")
		assert data["repository"]["name"] == "myrepo"
		assert data["schema_version"] == "1.1"
		assert data["packages"]["localboot_new"]["42.0-1337"]["url"] == "localboot_new_42.0-1337.opsi"
		assert data["packages"]["localboot_new"]["1.0-1"]["url"] == "localboot_new_1.0-1.opsi"
		assert data["packages"]["test-netboot"]["1.0-2"]["url"] == "subdir/test-netboot_1.0-2.opsi"

	# Update without scanning, keep name and change formats
	cmd = ["-l6", "manage-repo", "metafile", "update", str(repository_dir), "--format=json"]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	for suffix in formats:
		metafile = repository_dir / f"packages.{suffix}"
		if suffix == "json":
			data = read_metafile(metafile)
			assert data["repository"]["name"] == "myrepo"
			assert data["schema_version"] == "1.1"
			assert len(data["packages"]["localboot_new"]) == 3
			assert len(data["packages"]["test-netboot"]) == 1
		else:
			assert not metafile.exists()


def test_metafile_scan_packages(tmp_path: Path) -> None:
	repository_dir = tmp_path / "repository-dir"
	formats = ["json", "msgpack", "msgpack.zstd"]

	shutil.copytree(TEST_REPO, repository_dir)

	# Update must create metafiles if they do not exist
	cmd = ["-l6", "manage-repo", "metafile", "scan-packages", str(repository_dir)]
	returncode, out = run_cli(cmd)
	assert returncode == 1
	assert "No metadata files" in out

	cmd = ["-l6", "manage-repo", "metafile", "create", str(repository_dir)] + [f"--format={f}" for f in formats]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	for suffix in formats:
		data = read_metafile(repository_dir / f"packages.{suffix}")
		assert not data["packages"]

	cmd = ["-l6", "manage-repo", "metafile", "scan-packages", str(repository_dir)]
	returncode, out = run_cli(cmd)
	assert returncode == 0

	for suffix in formats:
		data = read_metafile(repository_dir / f"packages.{suffix}")
		assert len(data["packages"]["localboot_new"]) == 3
		assert len(data["packages"]["test-netboot"]) == 1


def test_metafile_add_package(tmp_path: Path) -> None:
	repository_dir = tmp_path / "repository-dir"
	formats = ["json", "msgpack", "msgpack.zstd"]

	repository_dir.mkdir()
	shutil.copy(TEST_REPO / "localboot_new_1.0-1.opsi", repository_dir)
	shutil.copy(TEST_REPO / "localboot_new_2.0-1.opsi", repository_dir)

	cmd = ["-l6", "manage-repo", "metafile", "create", str(repository_dir), "--scan"] + [f"--format={f}" for f in formats]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	# Check if update adds new package and deletes other entries for same package
	cmd = ["-l6", "manage-repo", "metafile", "add-package", str(repository_dir), str(repository_dir / "localboot_new_2.0-1.opsi")]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	for suffix in formats:
		data = read_metafile(repository_dir / f"packages.{suffix}")
		assert len(data["packages"]["localboot_new"]) == 1
		assert data["packages"]["localboot_new"]["2.0-1"]["url"] == "localboot_new_2.0-1.opsi"

	# Check if update adds new package and keeps others with --num-allowed-versions
	cmd = [
		"-l6",
		"manage-repo",
		"metafile",
		"add-package",
		"--num-allowed-versions=2",
		"--url=custom/url/localboot_new_1.0-1.opsi",
		"--compatibility=linux-all",
		"--compatibility=windows-x86",
		"--compatibility=macos-x64",
		str(repository_dir),
		str(repository_dir / "localboot_new_1.0-1.opsi"),
	]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	for suffix in formats:
		data = read_metafile(repository_dir / f"packages.{suffix}")
		assert len(data["packages"]["localboot_new"]) == 2
		assert data["packages"]["localboot_new"]["1.0-1"]["url"] == "custom/url/localboot_new_1.0-1.opsi"
		assert data["packages"]["localboot_new"]["2.0-1"]["url"] == "localboot_new_2.0-1.opsi"
		assert data["packages"]["localboot_new"]["1.0-1"]["compatibility"] == [
			{"os": "linux", "arch": "all"},
			{"os": "windows", "arch": "x86"},
			{"os": "macos", "arch": "x64"},
		]

	for compatibility in ("linux-invalid", "invalid-all", "linux", "all", "linux-amd64"):
		cmd = [
			"-l6",
			"manage-repo",
			"metafile",
			"add-package",
			str(repository_dir),
			str(repository_dir / "localboot_new_2.0-1.opsi"),
			f"--compatibility={compatibility}",
		]
		returncode, _ = run_cli(cmd)
		assert returncode == 1


def test_metafile_add_package_same_version(tmp_path: Path) -> None:
	repository_dir = tmp_path / "repository-dir"
	formats = ["json", "msgpack", "msgpack.zstd"]

	(repository_dir / "subdir").mkdir(parents=True)
	shutil.copy(TEST_REPO / "localboot_new_1.0-1.opsi", repository_dir)
	shutil.copy(TEST_REPO / "localboot_new_1.0-1.opsi", repository_dir / "subdir")
	# same version in different paths -> same RepoMetaPackage instance with .url as list

	cmd = ["-l6", "manage-repo", "metafile", "create", str(repository_dir), "--scan"] + [f"--format={f}" for f in formats]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	for suffix in formats:
		data = read_metafile(repository_dir / f"packages.{suffix}")
		package = data["packages"]["localboot_new"]["1.0-1"]
		assert isinstance(package["url"], list)
		assert "localboot_new_1.0-1.opsi" in package["url"]
		assert "subdir/localboot_new_1.0-1.opsi" in package["url"]


def test_metafile_remove_package(tmp_path: Path) -> None:
	repository_dir = tmp_path / "repository-dir"
	formats = ["json", "msgpack", "msgpack.zstd"]

	repository_dir.mkdir()
	shutil.copy(TEST_REPO / "localboot_new_1.0-1.opsi", repository_dir)
	shutil.copy(TEST_REPO / "localboot_new_2.0-1.opsi", repository_dir)

	cmd = ["-l6", "manage-repo", "metafile", "create", str(repository_dir), "--scan"] + [f"--format={f}" for f in formats]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	cmd = ["-l6", "manage-repo", "metafile", "remove-package", str(repository_dir), "localboot_new", "2.0-1"]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	for suffix in formats:
		data = read_metafile(repository_dir / f"packages.{suffix}")
		assert len(data["packages"]["localboot_new"]) == 1
		assert data["packages"]["localboot_new"]["1.0-1"]

	cmd = ["-l6", "manage-repo", "metafile", "remove-package", str(repository_dir), "localboot_new", "1.0-1"]
	returncode, _ = run_cli(cmd)
	assert returncode == 0

	for suffix in formats:
		data = read_metafile(repository_dir / f"packages.{suffix}")
		assert "localboot_new" not in data["packages"]
