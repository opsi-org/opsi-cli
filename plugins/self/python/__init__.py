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
from typing import Optional

import psutil  # type: ignore[import]
import rich_click as click  # type: ignore[import]
from click.shell_completion import get_completion_class  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]
from rich import print as rich_print
from rich.tree import Tree

from opsicli import __version__ as opsi_cli_version
from opsicli.config import ConfigValueSource, config
from opsicli.io import get_console
from opsicli.plugin import OPSICLIPlugin, plugin_manager
from opsicli.types import File
from opsicli.utils import add_to_env_variable

__version__ = "0.1.1"

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


def get_binary_path(system: bool = False) -> Path:
	if platform.system().lower() in ("linux", "darwin"):
		if system:
			return Path("/usr/local/bin/opsi-cli")
		return Path.home() / ".local/bin/opsi-cli"
	if platform.system().lower() == "windows":
		if system:
			return Path(r"c:\opsi.org\opsi-cli\opsi-cli.exe")
		return Path(r"~\AppData\Local\Programs\opsi-cli\opsi-cli.exe").expanduser()
	raise RuntimeError(f"Invalid platform {platform.system()}")


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
	"--no-add-to-path",
	is_flag=True,
	help="Do not add binary location to PATH.",
	default=False,
	show_default=True,
)
def install(system: bool, binary_path: Optional[Path] = None, no_add_to_path: bool = False) -> None:
	"""
	opsi-cli self install subcommand.

	Installs opsi-cli binary and configuration files to the system.
	"""
	binary_path = binary_path or get_binary_path(system=system)
	logger.notice("Copying %s to %s", sys.executable, binary_path)
	if not binary_path.parent.exists():
		binary_path.parent.mkdir(parents=True)
	try:
		shutil.copy(sys.executable, binary_path)
	except shutil.SameFileError:
		logger.warning("'%s' and '%s' are the same file", sys.executable, binary_path)
	source = ConfigValueSource.CONFIG_FILE_SYSTEM if system else ConfigValueSource.CONFIG_FILE_USER
	config.write_config_files(sources=[source])
	logger.debug("PATH is '%s'", os.environ.get("PATH", ""))
	if not no_add_to_path and str(binary_path.parent) not in os.environ.get("PATH", ""):
		add_to_env_variable("PATH", str(binary_path.parent), system=system)


@cli.command(short_help="Uninstall opsi-cli locally")
@click.option(
	"--system",
	is_flag=True,
	help="Uninstall system-wide.",
	default=False,
	show_default=True,
)
@click.option(
	"--binary-path",
	type=File,
	help="File path to find binary at.",
)
def uninstall(system: bool, binary_path: Optional[Path] = None) -> None:
	"""
	opsi-cli self uninstall subcommand.

	Uninstalls opsi-cli binary and configuration files from the system.
	"""
	binary_path = binary_path or get_binary_path(system=system)
	logger.notice("Removing binary from %s", binary_path)
	try:
		binary_path.unlink()
	except FileNotFoundError:
		logger.warning("'%s' not found!", binary_path)
	config_file = config.config_file_system if system else config.config_file_user
	if config_file and config_file.exists():
		config_file.unlink()


@cli.command(name="show-structure", short_help="Print structure of opsi-cli commands")
def show_structure() -> None:
	"""
	opsi-cli self show-structure subcommand.

	Prints the command structure of this opsi-cli instance.
	"""

	def add_sub_structure(item: click.Command | OPSICLIPlugin, tree: Tree):
		if isinstance(item, OPSICLIPlugin):
			branch = tree.add(f"{item.cli.name} [grey53]({item.version})[/grey53]", guide_style="green")
			if isinstance(item.cli, click.Group):
				for sub_item in item.cli.commands.values():
					add_sub_structure(sub_item, branch)
		elif isinstance(item, click.Group):
			branch = tree.add(item.name, guide_style="yellow")
			for sub_item in item.commands.values():
				add_sub_structure(sub_item, branch)
		elif isinstance(item, click.Command):
			tree.add(item.name)

	tree = Tree(f"opsi-cli [grey53]({opsi_cli_version})[/grey53]", guide_style="bold bright_blue")
	for cmd in sorted([plugin for plugin in plugin_manager.plugins if plugin.cli], key=lambda plugin: plugin.cli.name):
		add_sub_structure(cmd, tree)
	rich_print(tree)


class SelfPlugin(OPSICLIPlugin):
	id: str = "self"  # pylint: disable=invalid-name
	name: str = "Self"
	description: str = "Manage opsi-cli"
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
