"""
test_self
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from opsicommon.system.info import is_windows

from opsicli.config import config
from opsicli.plugin import plugin_manager
from plugins.self.python import get_binary_path, get_binary_paths

from .utils import run_cli, temp_context


def test_get_binary_paths() -> None:
	user_path = get_binary_path(system=False)
	system_path = get_binary_path(system=True)
	assert get_binary_paths("user") == [user_path]
	assert get_binary_paths("system") == [system_path]
	paths = get_binary_paths("all")
	assert user_path in paths
	assert system_path in paths
	if is_windows():
		assert get_binary_paths(r"c:\windows") == [Path(r"c:\windows\opsi-cli.exe")]
		assert get_binary_paths(Path(r"c:\windows")) == [Path(r"c:\windows\opsi-cli.exe")]
		assert get_binary_paths(r".\\") == [Path(r".\\opsi-cli.exe").absolute()]
	else:
		assert get_binary_paths("/tmp/") == [Path("/tmp/opsi-cli")]
		assert get_binary_paths(Path("/tmp/")) == [Path("/tmp/opsi-cli")]
		assert get_binary_paths("./") == [Path("./opsi-cli").absolute()]


def test_self_install() -> None:
	with temp_context() as tempdir, patch("opsicli.utils.user_is_admin", lambda: False):
		conffile = Path(tempdir) / "conffile.conf"
		config.config_file_user = conffile
		binary_path = Path(tempdir) / "out_binary"
		(exit_code, stdout, _stderr) = run_cli(["self", "install", "--location", str(binary_path), "--no-add-to-path"])
		print(stdout)
		assert exit_code == 0
		assert binary_path.exists()
		assert config.config_file_user.exists()


@pytest.mark.parametrize("location", ["current", "all"])
def test_self_upgrade(location: str) -> None:
	with patch("opsicli.utils.install_binary", lambda *args, **kwargs: None):
		cmd = ["-l", "7", "--dry-run", "self", "upgrade", "--location", location]
		exit_code, stdout, stderr = run_cli(cmd)
		print(stdout)
		print(stderr)
		assert "Would upgrade" in stdout


def test_self_uninstall() -> None:
	with temp_context() as tempdir, patch("opsicli.utils.user_is_admin", lambda: False):
		conffile = Path(tempdir) / "conffile.conf"
		config.config_file_user = conffile
		binary_path = Path(tempdir) / "out_binary"

		exit_code, _stdout, _stderr = run_cli(["self", "install", "--location", str(binary_path), "--no-add-to-path"])
		assert config.config_file_user.exists()

		exit_code, stdout, _stderr = run_cli(["self", "uninstall", "--location", str(binary_path)])
		print(stdout)
		assert exit_code == 0
		assert not binary_path.exists()
		assert not config.config_file_user.exists()


def test_setup_shell_completion(tmp_path: Path) -> None:
	plugin = plugin_manager.load_plugin("self")
	completion_config = tmp_path / "completion"
	mod_self = plugin.get_module()
	exit_code, stdout, stderr = run_cli(["self", "setup-shell-completion", "--completion-file", str(completion_config)])
	print(exit_code, stdout, stderr)

	assert exit_code == 0
	assert "Setting up auto completion for shell" in stdout
	assert completion_config.exists()
	cont = completion_config.read_text()
	assert cont.startswith(mod_self.START_MARKER + "\n")
	assert cont.endswith(mod_self.END_MARKER + "\n")
	completion_config.unlink()

	exit_code, stdout, stderr = run_cli(["self", "setup-shell-completion", "--shell", "zsh", "--completion-file", str(completion_config)])
	assert exit_code == 0
	assert "Setting up auto completion for shell 'zsh'" in stdout
	cont = completion_config.read_text()
	assert cont.startswith(mod_self.START_MARKER + "\n")
	assert "#compdef opsi-cli" in cont
	assert cont.endswith(mod_self.END_MARKER + "\n")
	completion_config.unlink()

	exit_code, stdout, stderr = run_cli(["self", "setup-shell-completion", "--shell", "invalid"])
	assert exit_code == 2
	assert "'invalid' is not one of " in stderr


def test_command_structure() -> None:
	exit_code, stdout, _stderr = run_cli(["self", "command-structure"])
	mod_self = plugin_manager.load_plugin("self").get_module()
	print(stdout)
	assert exit_code == 0
	assert stdout.startswith("opsi-cli")
	assert f"self ({mod_self.__version__})\n" in stdout
