"""
test_self
"""

from pathlib import Path

import pytest

from opsicli.config import config
from opsicli.plugin import plugin_manager

from .conftest import PLATFORM
from .utils import run_cli, temp_context


def test_self_install() -> None:
	with temp_context() as tempdir:
		conffile = Path(tempdir) / "conffile.conf"
		config.config_file_user = conffile
		binary_path = Path(tempdir) / "out_binary"
		(exit_code, output) = run_cli(["self", "install", f"--binary-path={binary_path}", "--no-add-to-path"])
		print(output)
		assert exit_code == 0
		assert binary_path.exists()
		assert config.config_file_user.exists()


def test_self_uninstall() -> None:
	with temp_context() as tempdir:
		conffile = Path(tempdir) / "conffile.conf"
		config.config_file_user = conffile
		binary_path = Path(tempdir) / "out_binary"
		(exit_code, _) = run_cli(["self", "install", f"--binary-path={binary_path}", "--no-add-to-path"])
		(exit_code, output) = run_cli(["self", "uninstall", f"--binary-path={binary_path}"])
		print(output)
		assert exit_code == 0
		assert not binary_path.exists()
		assert not config.config_file_user.exists()


@pytest.mark.posix
def test_setup_shell_completion(tmp_path: Path) -> None:
	plugin = plugin_manager.load_plugin("self")
	completion_config = tmp_path / "completion"
	mod_self = plugin.get_module()
	exit_code, output = run_cli(["self", "setup-shell-completion", "--completion-file", str(completion_config)])
	print(exit_code, output)

	if PLATFORM == "windows":
		assert exit_code == 1
		return

	if PLATFORM == "darwin":
		assert exit_code == 1
		return

	assert exit_code == 0
	assert output == "Setting up auto completion for shell 'bash'.\nPlease restart your running shell for changes to take effect.\n"
	assert completion_config.exists()
	cont = completion_config.read_text()
	assert cont.startswith(mod_self.START_MARKER + "\n")
	assert "_opsi_cli_completion() {" in cont
	assert cont.endswith(mod_self.END_MARKER + "\n")
	completion_config.unlink()

	exit_code, output = run_cli(["self", "setup-shell-completion", "--shell", "zsh", "--completion-file", str(completion_config)])
	assert exit_code == 0
	assert output == "Setting up auto completion for shell 'zsh'.\n"
	cont = completion_config.read_text()
	assert cont.startswith(mod_self.START_MARKER + "\n")
	assert "#compdef opsi-cli" in cont
	assert cont.endswith(mod_self.END_MARKER + "\n")
	completion_config.unlink()

	exit_code, output = run_cli(["self", "setup-shell-completion", "--shell", "invalid"])
	assert exit_code == 2
	assert "'invalid' is not one of 'auto', 'all', 'zsh', 'bash', 'fish'." in output


def test_command_structure() -> None:
	exit_code, output = run_cli(["self", "command-structure"])
	mod_self = plugin_manager.load_plugin("self").get_module()
	print(output)
	assert exit_code == 0
	assert output.startswith("opsi-cli")
	assert f"self ({mod_self.__version__})\n" in output
