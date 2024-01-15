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
import tempfile
from pathlib import Path

import psutil  # type: ignore[import]
import rich_click as click  # type: ignore[import]
from click.shell_completion import get_completion_class  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]
from rich import print as rich_print
from rich.tree import Tree

from opsicli import __version__ as opsi_cli_version
from opsicli.config import ConfigValueSource, config
from opsicli.io import get_console
from opsicli.plugin import OPSICLIPlugin, plugin_manager
from opsicli.types import File
from opsicli.utils import (
	add_to_env_variable,
	download,
	get_opsi_cli_filename,
	replace_binary,
	user_is_admin,
)

__version__ = "0.2.0"

START_MARKER = "### Added by opsi-cli ###"
END_MARKER = "### /Added by opsi-cli ###"

logger = get_logger("opsicli")


def get_completion_config_path(shell: str) -> Path:
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


SUPPORTED_SHELLS = ["zsh", "bash", "fish", "powershell"]


def get_running_shell() -> str:
	running_shell = psutil.Process(os.getpid()).parent().name()
	logger.debug("Parent process: %s", running_shell)
	if not running_shell or running_shell not in SUPPORTED_SHELLS:
		logger.info("Did not get shell from parent process.")
		try:
			running_shell = Path(os.environ["SHELL"]).name
		except KeyError:
			logger.warning("Did not get shell from environment.")
			if platform.system().lower() == "windows":
				logger.notice("Running on windows, assuming powershell")
				running_shell = "powershell"
	if running_shell not in SUPPORTED_SHELLS:
		raise ValueError("Did not determine valid running shell")
	return running_shell


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
@click.option(
	"--completion-file",
	type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
	help="Use this file to store shell completions instead of the shell-default.",
	hidden=True,
)
@click.pass_context
def setup_shell_completion(ctx: click.Context, shell: str, completion_file: Path) -> None:  # pylint: disable=too-many-branches
	"""
	opsi-cli self setup_shell_completion subcommand.
	"""
	shells = []
	running_shell = get_running_shell()
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
	if len(shells) > 1 and completion_file:
		raise RuntimeError(f"Attempting to write multiple shell completions ({shells}) into one file {completion_file}")
	entry_pattern = re.compile(rf"{START_MARKER}.*?{END_MARKER}\n", flags=re.DOTALL)
	console = get_console()
	for shell_ in shells:
		console.print(f"Setting up auto completion for shell [bold cyan]{shell_!r}[/bold cyan].")
		conf_file = completion_file or get_completion_config_path(shell_)
		if not conf_file.parent.exists():
			conf_file.parent.mkdir(parents=True)
		data = ""
		if conf_file.exists():
			data = conf_file.read_text(encoding="utf-8")
		data = re.sub(entry_pattern, "", data)

		comp_cls = get_completion_class(shell_)
		if not comp_cls:
			raise RuntimeError(f"Failed to get completion class for shell {shell_!r}")
		if not ctx or not ctx.parent or not ctx.parent.command:
			raise RuntimeError("Invalid context for parent command")
		comp = comp_cls(cli=ctx.parent.command, ctx_args={}, prog_name="opsi-cli", complete_var="_OPSI_CLI_COMPLETE")
		if config.dry_run:
			logger.notice("Not writing completion files as --dry-run is set.")
		else:
			conf_file.write_text(data + f"{START_MARKER}\n{comp.source()}\n{END_MARKER}\n", encoding="utf-8")
	if running_shell in shells:
		# os.execvp(running_shell, [running_shell])
		console.print("Please restart your running shell for changes to take effect.")


@cli.command(short_help="Install opsi-cli locally")
@click.option(
	"--system/--no-system",
	is_flag=True,
	help="Install system-wide.",
	default=user_is_admin(),
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
def install(system: bool, binary_path: Path | None = None, no_add_to_path: bool = False) -> None:
	"""
	opsi-cli self install subcommand.

	Installs opsi-cli binary and configuration files to the system.
	"""
	binary_path = binary_path or get_binary_path(system=system)
	src_binary = sys.executable
	ziplauncher_binary = os.environ.get("ZIPLAUNCHER_BINARY")
	if ziplauncher_binary and os.path.exists(ziplauncher_binary):
		src_binary = ziplauncher_binary

	logger.notice("Copying %s to %s", src_binary, binary_path)
	if not binary_path.parent.exists():
		binary_path.parent.mkdir(parents=True)
	try:
		if config.dry_run:
			logger.notice("Not writing binary as --dry-run is set.")
		else:
			shutil.copy(src_binary, binary_path)
	except shutil.SameFileError:
		logger.warning("'%s' and '%s' are the same file", src_binary, binary_path)
	source = ConfigValueSource.CONFIG_FILE_SYSTEM if system else ConfigValueSource.CONFIG_FILE_USER
	if config.dry_run:
		logger.notice("Not writing config files as --dry-run is set.")
	else:
		config.write_config_files(sources=[source])
		logger.debug("PATH is '%s'", os.environ.get("PATH", ""))
		if not no_add_to_path and str(binary_path.parent) not in os.environ.get("PATH", ""):
			add_to_env_variable("PATH", str(binary_path.parent), system=system)
	rich_print(f"opsi-cli installed to '{binary_path}'.")
	rich_print("Run 'opsi-cli self setup-shell-completion' to setup shell completion.")


@cli.command(short_help="upgrade local opsi-cli instance")
@click.option(
	"--branch",
	type=str,
	help="Branch from which to pull.",
	default="stable",
	show_default=True,
)
@click.option(
	"--source-url",
	type=str,
	help="Url from which to pull.",
	default="https://tools.43.opsi.org",
	show_default=True,
)
def upgrade(branch: str, source_url: str) -> None:
	"""
	opsi-cli self upgrade subcommand.

	Upgrades opsi-cli binary from remote source.
	"""
	current_binary = Path(sys.executable)
	ziplauncher_binary = os.environ.get("ZIPLAUNCHER_BINARY")
	if ziplauncher_binary and os.path.exists(ziplauncher_binary):
		current_binary = Path(ziplauncher_binary)
	with tempfile.TemporaryDirectory() as tmpdir_name:
		tmp_dir = Path(tmpdir_name)
		new_binary = download(f"{source_url}/{branch}/{get_opsi_cli_filename()}", tmp_dir, make_executable=True)
		try:
			new_version = subprocess.check_output([str(new_binary), "--version"]).decode("utf-8").strip()
		except subprocess.CalledProcessError as error:
			logger.error("New binary not working: %s", error)
			raise
		if config.dry_run:
			logger.notice("Not replacing current binary as --dry-run is set.")
		else:
			replace_binary(current=current_binary, new=new_binary)
	rich_print(f"opsi-cli upgraded to '{new_version}'.")


@cli.command(short_help="Uninstall opsi-cli locally")
@click.option(
	"--system/--no-system",
	is_flag=True,
	help="Uninstall system-wide.",
	default=user_is_admin(),
	show_default=True,
)
@click.option(
	"--binary-path",
	type=File,
	help="File path to find binary at.",
)
def uninstall(system: bool, binary_path: Path | None = None) -> None:
	"""
	opsi-cli self uninstall subcommand.

	Uninstalls opsi-cli binary and configuration files from the system.
	"""
	binary_path = binary_path or get_binary_path(system=system)
	if binary_path.exists():
		if config.dry_run:
			logger.notice("Not removing binary from %s as --dry-run is set.", binary_path)
		else:
			logger.notice("Removing binary from %s", binary_path)
			binary_path.unlink()

	config_file = config.config_file_system if system else config.config_file_user
	if config_file and config_file.exists():
		if config.dry_run:
			logger.notice("Not removing config file %s as --dry-run is set.", config_file)
		else:
			logger.debug("Removing config file %s", config_file)
			config_file.unlink()
	rich_print("opsi-cli uninstalled.")


@cli.command(name="command-structure", short_help="Print structure of opsi-cli commands")
def command_structure() -> None:
	"""
	opsi-cli self command-structure subcommand.

	Prints the command structure of this opsi-cli instance.
	"""

	def add_sub_structure(item: click.Command | OPSICLIPlugin, tree: Tree) -> None:
		if isinstance(item, OPSICLIPlugin) and item.cli:
			branch = tree.add(f"{item.cli.name} [grey53]({item.version})[/grey53]", guide_style="green")
			if isinstance(item.cli, click.Group):
				for sub_item in item.cli.commands.values():
					add_sub_structure(sub_item, branch)
		elif isinstance(item, click.Group) and item.name:
			branch = tree.add(item.name, guide_style="yellow")
			for sub_item in item.commands.values():
				add_sub_structure(sub_item, branch)
		elif isinstance(item, click.Command) and item.name:
			tree.add(item.name)

	tree = Tree(f"opsi-cli [grey53]({opsi_cli_version})[/grey53]", guide_style="bold bright_blue")
	for plugin_id in sorted(plugin_manager.plugins):
		plugin = plugin_manager.load_plugin(plugin_id)
		add_sub_structure(plugin, tree)
	rich_print(tree)


class SelfPlugin(OPSICLIPlugin):
	name: str = "Self"
	description: str = "Manage opsi-cli"
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
