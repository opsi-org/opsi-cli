"""
opsi-cli basic command line interface for opsi

self plugin
"""

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import psutil  # type: ignore[import]
import rich_click as click  # type: ignore[import]
from click.shell_completion import get_completion_class  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.config import ConfigValueSource, config
from opsicli.io import get_console
from opsicli.plugin import OPSICLIPlugin
from opsicli.types import File
from opsicli.utils import add_to_env_variable

__version__ = "0.1.0"

START_MARKER = "### Added by opsi-cli ###"
END_MARKER = "### /Added by opsi-cli ###"


def get_completion_config_path(shell: str):
	if shell == "fish":
		return Path("~/.config/fish/completions/opsi-cli.fish").expanduser().resolve()
	if shell == "bash":
		return Path("~/.bash_completion").expanduser().resolve()
	if shell == "zsh":
		return Path("~/.zshrc").expanduser().resolve()
	if shell == "powershell":
		return Path(subprocess.check_output(["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "echo $profile"]).decode().strip())
	raise ValueError("Shell {shell!r} is not supported.")


@click.group(name="self", short_help="Manage opsi-cli")
@click.version_option(__version__, message="self plugin, version %(version)s")
def cli() -> None:  # pylint: disable=unused-argument
	"""
	opsi-cli self command.
	This command is used to manage opsi-cli.
	"""
	logger.trace("self command")


SUPPORTED_SHELLS = ["zsh", "bash", "fish"]


@cli.command(short_help="Setup shell completion")
@click.option(
	"--shell",
	metavar="SHELL-NAME",
	type=click.Choice(["auto", "all"] + SUPPORTED_SHELLS, case_sensitive=False),
	help=(
		"Select a shell to setup completion for.\n\n"
		f"Supported shells are: {', '.join(f'[metavar]{s}[/metavar]' for s in SUPPORTED_SHELLS)}.\n\n"
		"Use [metavar]all[/metavar] to setup all available and supported shells.\n\n"
		"Use [metavar]auto[/metavar] to setup the running shell."
	),
	default="auto",
	show_default=True,
)
@click.pass_context
def setup_shell_completion(ctx: click.Context, shell: str) -> None:  # pylint: disable=too-many-branches
	"""
	opsi-cli self setup_shell_completion subcommand.
	"""
	shells = []
	running_shell = psutil.Process(os.getpid()).parent().name()
	if not running_shell or running_shell not in SUPPORTED_SHELLS:
		running_shell = Path(os.environ["SHELL"]).name

	if shell == "auto":
		if running_shell not in SUPPORTED_SHELLS:
			raise ValueError(f"Shell {running_shell!r} is not supported")
		shells = [running_shell]
	elif shell == "all":
		for supported_shell in SUPPORTED_SHELLS:
			path = shutil.which(supported_shell)
			if path:
				logger.info("Shell %r found", path)
				shells.append(supported_shell)
		if not shells:
			raise ValueError("No supported shell found")
	else:
		shells = [shell]

	console = get_console()
	for shell_ in shells:
		console.print(f"Setting up auto completion for shell [bold cyan]{shell_!r}[/bold cyan].")
		conf_file = get_completion_config_path(shell_)
		if not conf_file.parent.exists():
			conf_file.parent.mkdir(parents=True)
		data = ""
		if conf_file.exists():
			data = conf_file.read_text(encoding="utf-8")
		data = re.sub(rf"{START_MARKER}.*?{END_MARKER}\n", "", data, flags=re.DOTALL)

		comp_cls = get_completion_class(shell_)
		if not comp_cls:
			raise RuntimeError(f"Failed to get completion class for shell {shell_!r}")
		if not ctx or not ctx.parent or not ctx.parent.command:
			raise RuntimeError("Invalid context for parent command")
		comp = comp_cls(cli=ctx.parent.command, ctx_args={}, prog_name="opsi-cli", complete_var="_OPSI_CLI_COMPLETE")
		conf_file.write_text(data + f"{START_MARKER}\n{comp.source()}\n{END_MARKER}\n", encoding="utf-8")
	if running_shell in shells:
		# os.execvp(running_shell, [running_shell])
		console.print("Please restart your running shell for changes to take effect.")


@cli.command(short_help="Install opsi-cli locally")
@click.option(
	"--system",
	is_flag=True,
	help="Install system-wide.",
	default=False,
	show_default=True,
)
@click.option(
	"--binary-path",
	type=File,
	help="File path to store binary at.",
)
@click.option(
	"--ignore-environment",
	is_flag=True,
	help="Do not set PATH environment.",
	default=False,
	show_default=True,
)
def install(system: bool, binary_path: Path = None, ignore_environment: bool = False) -> None:
	"""
	opsi-cli self install subcommand.

	Installs opsi-cli binary and configuration files to the system.
	"""
	if not binary_path:
		if platform.system().lower() in ("linux", "darwin"):
			if system:
				binary_path = Path("/") / "usr" / "local" / "bin" / "opsi-cli"
			else:
				binary_path = Path.home() / ".local" / "bin" / "opsi-cli"
		elif platform.system().lower() == "windows":
			if system:
				raise RuntimeError("System-wide installation disabled for windows (for now at least).")
			binary_path = Path.home() / "AppData" / "Local" / "Programs" / "opsi-cli" / "opsi-cli.exe"
		else:
			raise RuntimeError(f"Invalid platform {platform.system()}")
	logger.notice("Copying %s to %s", sys.executable, binary_path)
	if not binary_path.parent.exists():
		binary_path.parent.mkdir(parents=True)
	try:
		shutil.copy(sys.executable, binary_path)
	except shutil.SameFileError:
		logger.warning("'%s' and '%s' are the same file", sys.executable, binary_path)
	source = ConfigValueSource.CONFIG_FILE_SYSTEM if system else ConfigValueSource.CONFIG_FILE_USER
	config.write_config_files(sources=[source])
	if not ignore_environment and str(binary_path.parent) not in os.environ.get("PATH", ""):
		add_to_env_variable("PATH", binary_path.parent)


class SelfPlugin(OPSICLIPlugin):
	id: str = "self"  # pylint: disable=invalid-name
	name: str = "Self"
	description: str = "Manage opsi-cli"
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
