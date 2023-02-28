"""
test_self
"""

import sys
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from opsicli.__main__ import main
from opsicli.config import config
from opsicli.plugin import plugin_manager

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


def hide_test_setup_shell_completion(tmp_path: Path) -> None:
	plugin_manager.load_plugin(Path("plugins/self"))
	completion_config = tmp_path / "completion"
	mod_self_name, mod_self = [(n, m) for n, m in sys.modules.items() if n.endswith("plugins/self")][0]
	with (
		patch(f"{mod_self_name}.get_running_shell", lambda: "bash"),
		patch(f"{mod_self_name}.get_completion_config_path", lambda x: completion_config),
	):
		runner = CliRunner()
		result = runner.invoke(main, ["self", "setup-shell-completion"])
		assert result.exit_code == 0
		assert (
			result.output == "Setting up auto completion for shell 'bash'.\nPlease restart your running shell for changes to take effect.\n"
		)
		cont = completion_config.read_text()
		assert cont.startswith(mod_self.START_MARKER + "\n")
		assert "_opsi_cli_completion() {" in cont
		assert cont.endswith(mod_self.END_MARKER + "\n")
		completion_config.unlink()

		runner = CliRunner()
		result = runner.invoke(main, ["self", "setup-shell-completion", "--shell", "zsh"])
		assert result.exit_code == 0
		assert result.output == "Setting up auto completion for shell 'zsh'.\n"
		cont = completion_config.read_text()
		assert cont.startswith(mod_self.START_MARKER + "\n")
		assert "#compdef opsi-cli" in cont
		assert cont.endswith(mod_self.END_MARKER + "\n")
		completion_config.unlink()

		runner = CliRunner()
		result = runner.invoke(main, ["self", "setup-shell-completion", "--shell", "invalid"])
		assert result.exit_code == 2
		assert "Invalid value for '--shell': 'invalid' is not one of 'auto', 'all', 'zsh', 'bash', 'fish'." in result.output


def hide_test_command_structure() -> None:
	runner = CliRunner()
	result = runner.invoke(main, ["self", "command-structure"])
	mod_self = [m for n, m in sys.modules.items() if n.endswith("plugins/self")][0]
	assert result.exit_code == 0
	assert result.output.startswith("opsi-cli")
	assert f"━━ self ({mod_self.__version__})\n" in result.output
