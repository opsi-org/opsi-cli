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
from opsicommon.system.info import is_posix, is_windows
from rich.tree import Tree

from opsicli import __version__ as opsi_cli_version
from opsicli.config import ConfigValueSource, config
from opsicli.io import Attribute, Metadata, get_console, write_output
from opsicli.plugin import OPSICLIPlugin, plugin_manager
from opsicli.types import File
from opsicli.utils import add_to_env_variable, download, get_opsi_cli_download_filename, install_binary, retry, user_is_admin

installed_version_metadata = Metadata(
	attributes=[
		Attribute(id="path", description="Location of the binary", identifier=True, data_type="str"),
		Attribute(id="version", description="Version of the binary", data_type="str"),
		Attribute(id="default", description="Default binary (first in PATH)?", data_type="bool"),
		Attribute(id="writable", description="Is the binary writable?", data_type="bool"),
	]
)

__version__ = "0.3.0"

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
	raise ValueError(f"Shell {shell!r} is not supported.")


def get_binary_name() -> str:
	if is_windows():
		return "opsi-cli.exe"
	return "opsi-cli"


def get_binary_path(system: bool = False) -> Path:
	if is_posix():
		if system:
			return Path("/usr/local/bin") / get_binary_name()
		return Path.home() / ".local/bin" / get_binary_name()
	if is_windows():
		if system:
			return Path(r"c:/opsi.org/opsi-cli") / get_binary_name()
		return Path.home() / "AppData/Local/Programs/opsi-cli" / get_binary_name()
	raise RuntimeError(f"Platform '{platform.system()}' not supported")


def get_current_binary_path() -> Path:
	current_binary = Path(sys.executable)
	ziplauncher_binary = os.environ.get("ZIPLAUNCHER_BINARY")
	if ziplauncher_binary and os.path.exists(ziplauncher_binary):
		current_binary = Path(ziplauncher_binary)
	return current_binary


def get_binary_paths(location: str | Path) -> list[Path]:
	if isinstance(location, str):
		if location == "current":
			return [get_current_binary_path()]
		if location == "all":
			return list(set([get_binary_path(system=False), get_binary_path(system=True)] + list(get_installed_versions())))
		if location == "user":
			return [get_binary_path(system=False)]
		elif location == "system":
			return [get_binary_path(system=True)]
		location = Path(location)
	location = location.expanduser().absolute()
	if location.is_dir():
		location = location / get_binary_name()
	return [location]


def get_installed_versions() -> dict[Path, str]:
	installed_versions = {}
	usr_path = get_binary_path(system=False).parent
	sys_path = get_binary_path(system=True).parent
	paths = [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep)]
	if usr_path not in paths:
		paths.insert(0, usr_path)
	if sys_path not in paths:
		paths.append(sys_path)
	for path in paths:
		binary = path / get_binary_name()
		if not binary.exists():
			continue
		try:
			version = subprocess.check_output([str(binary), "--version"]).decode("utf-8").strip().split()[-1]
		except subprocess.CalledProcessError:
			version = "?"
		installed_versions[binary] = version
	return installed_versions


def print_installed_versions() -> None:
	data = []
	installed_versions = get_installed_versions()
	for idx, binary in enumerate(installed_versions):
		data.append(
			{
				"path": binary,
				"version": installed_versions[binary],
				"default": idx == 0,
				"writable": os.access(binary, os.W_OK),
			}
		)
	write_output(data, installed_version_metadata)


@click.group(name="self", short_help="Manage opsi-cli")
@click.version_option(__version__, message="self plugin, version %(version)s")
def cli() -> None:
	"""
	opsi-cli self command.
	This command is used to manage opsi-cli.
	"""
	logger.trace("self command")


SUPPORTED_SHELLS = ["zsh", "bash", "fish", "powershell"]


def get_running_shell() -> str:
	proc = psutil.Process(os.getpid())
	for ancestor_name in [proc.parent().name(), proc.parent().parent().name()]:
		logger.debug("Checking if ancestor process  %r is a supported shell", ancestor_name)
		if ancestor_name in SUPPORTED_SHELLS:
			logger.info("Found supported shell %r in ancestor process", ancestor_name)
			return ancestor_name
	logger.debug("Did not find a supported shell shell in ancestor process")

	env_shell = Path(os.environ.get("SHELL", "")).name
	if env_shell and env_shell in SUPPORTED_SHELLS:
		logger.info("Found supported shell %r in SHELL environment variable", env_shell)
		return env_shell
	logger.debug("Did not find a supported shell in SHELL environment variable (SHELL=%r)", env_shell)

	if platform.system().lower() == "windows":
		logger.info("Running on windows, assuming powershell")
		return "powershell"

	raise ValueError("No supported running shell could be determined")


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
def setup_shell_completion(ctx: click.Context, shell: str, completion_file: Path) -> None:
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

		if not conf_file.parent.exists() and not config.dry_run:
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
	"--location",
	type=str,
	help="Where to install opsi-cli. Can be 'user' (default), 'system', 'all' or an explicit path.\n",
	default="user",
)
@click.option(
	"--no-add-to-path",
	is_flag=True,
	help="Do not add binary location to PATH.",
	default=False,
	show_default=True,
)
@click.option(
	"--system/--no-system",
	is_flag=True,
	help="Install system-wide (deprecated, please use --location).",
	default=None,
	show_default=True,
)
@click.option(
	"--binary-path",
	type=File,
	help="File path to store binary at (deprecated, please use --location).",
)
def install(location: str, no_add_to_path: bool, system: bool | None, binary_path: Path | None = None) -> None:
	"""
	opsi-cli self install subcommand.

	Installs opsi-cli binary and configuration files to the system.
	"""
	if binary_path:
		location = str(binary_path)
	elif system is not None:
		location = "system" if system else "user"

	binary_paths = get_binary_paths(location)

	src_binary = sys.executable
	ziplauncher_binary = os.environ.get("ZIPLAUNCHER_BINARY")
	if ziplauncher_binary and os.path.exists(ziplauncher_binary):
		src_binary = ziplauncher_binary

	exit_code = 0
	for binary in binary_paths:
		logger.notice("Copying '%s' to '%s'", src_binary, binary)
		try:
			if config.dry_run:
				logger.notice("Would copy '%s' to '%s', but --dry-run is set", src_binary, binary)
				get_console().print(f"Would install opsi-cli to '{binary}', but --dry-run is set.")
			else:
				logger.notice("Copying '%s' to '%s'", src_binary, binary)
				get_console().print(f"Installing opsi-cli to '{binary}'.")
				install_binary(source=src_binary, destination=binary)
		except Exception as err:
			exit_code = 1
			logger.error("Failed to install opsi-cli to '%s': %s", binary, err)
			get_console().print(f"[red]Failed to install opsi-cli to '{binary}': {err}[/red]")
			continue

		sys_install = user_is_admin() and not binary.parent.is_relative_to(Path.home())
		source = ConfigValueSource.CONFIG_FILE_SYSTEM if sys_install else ConfigValueSource.CONFIG_FILE_USER
		if config.dry_run:
			logger.notice("Not writing config files as --dry-run is set.")
		else:
			config.write_config_files(sources=[source])
			logger.debug("PATH is '%s'", os.environ.get("PATH", ""))
			if not no_add_to_path and str(binary.parent) not in os.environ.get("PATH", ""):
				add_to_env_variable("PATH", str(binary.parent), system=sys_install)

	get_console().print("Run 'opsi-cli self setup-shell-completion' to setup shell completion.")
	sys.exit(exit_code)


@cli.command(short_help="Upgrade local opsi-cli installation")
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
	help="URL from which to pull.",
	default="https://tools.43.opsi.org",
	show_default=True,
)
@click.option(
	"--location",
	type=str,
	help="Where to install opsi-cli. Can be 'current' (default), 'user', 'system', 'all' or an explicit path.\n",
	default="current",
)
def upgrade(branch: str, source_url: str, location: str) -> None:
	"""
	opsi-cli self upgrade subcommand.

	Upgrades local opsi-cli installation from remote source.
	"""

	binary_paths = get_binary_paths(location)
	if location == "all":
		current_binary_path = get_current_binary_path()
		if current_binary_path not in binary_paths:
			binary_paths.append(current_binary_path)
	binary_paths = [p for p in binary_paths if p.exists()]

	exit_code = 0
	with tempfile.TemporaryDirectory() as tmpdir_name:
		tmp_dir = Path(tmpdir_name)

		@retry(retries=2, wait=1.0, exceptions=[OSError, PermissionError, subprocess.CalledProcessError])
		def download_binary() -> tuple[Path, str]:
			download_url = f"{source_url}/{branch}/{get_opsi_cli_download_filename()}"
			get_console().print(f"Downloading opsi-cli from '{download_url}'.")
			new_binary = download(download_url, tmp_dir, make_executable=True)
			try:
				new_version = subprocess.check_output([str(new_binary), "--version"]).decode("utf-8").strip().split()[-1]
				return new_binary, new_version
			except subprocess.CalledProcessError as error:
				logger.error("New binary not working: %s", error)
				raise

		new_binary, new_version = download_binary()

		for binary in binary_paths:
			try:
				if config.dry_run:
					logger.notice("Would replace '%s' with '%s', but --dry-run is set", binary, new_binary)
					get_console().print(f"Would upgrade '{binary}' to '{new_version}', but --dry-run is set.")
				else:
					logger.notice("Replacing '%s' with '%s'", binary, new_binary)
					get_console().print(f"Upgrading '{binary}' to '{new_version}'.")
					install_binary(destination=binary, source=new_binary)
			except Exception as err:
				exit_code = 1
				logger.error("Failed to install opsi-cli to '%s': %s", binary, err)
				get_console().print(f"[red]Failed to install opsi-cli to '{binary}': {err}[/red]")
				continue

	sys.exit(exit_code)


@cli.command(short_help="Uninstall local opsi-cli installation")
@click.option(
	"--location",
	type=str,
	help="Where to install opsi-cli. Can be 'user' (default), 'system', 'current', 'all' or an explicit path.\n",
	default="user",
)
@click.option(
	"--system/--no-system",
	is_flag=True,
	help="Install system-wide (deprecated, please use --location).",
	default=None,
	show_default=True,
)
@click.option(
	"--binary-path",
	type=File,
	help="File path to find binary at (deprecated, please use --location)",
)
def uninstall(location: str, system: bool | None = None, binary_path: Path | None = None) -> None:
	"""
	opsi-cli self uninstall subcommand.

	Uninstalls opsi-cli binaries and configuration files from the system.
	"""

	binary_paths = get_binary_paths(location)
	exit_code = 0
	for binary in binary_paths:
		try:
			if binary.exists():
				if config.dry_run:
					logger.notice("Would remove binary '%s', but --dry-run is set", binary)
					get_console().print(f"Would remove binary '{binary}', but --dry-run is set.")
				else:
					logger.notice("Removing binary '%s'", binary)
					get_console().print(f"Removing binary '{binary}'.")
					binary.unlink()
			else:
				logger.notice("Binary '%s' does not exist.", binary)
				get_console().print(f"Binary '{binary}' does not exist.")
		except Exception as err:
			exit_code = 1
			logger.error("Failed to remove binary '%s': %s", binary, err)
			get_console().print(f"[red]Failed to remove binary '{binary}': {err}[/red]")
			continue

		sys_install = user_is_admin() and not binary.parent.is_relative_to(Path.home())
		try:
			config_file = config.config_file_system if sys_install else config.config_file_user
			if config_file and config_file.exists():
				if config.dry_run:
					logger.notice("Would remove config file '%s', but --dry-run is set", config_file)
					get_console().print(f"Would remove config file '{config_file}', but --dry-run is set.")
				else:
					logger.notice("Removing config file '%s'", config_file)
					get_console().print(f"Removing config file '{config_file}'.")
					config_file.unlink()
		except Exception as err:
			exit_code = 1
			logger.error("Failed to remove config file '%s': %s", config_file, err)
			get_console().print(f"[red]Failed to remove config file '{config_file}': {err}[/red]")

	sys.exit(exit_code)


@cli.command(name="installed-versions", short_help="Show installed opsi-cli versions")
def installed_versions() -> None:
	"""
	Show all installed opsi-cli binaries and versions.
	"""
	print_installed_versions()


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
	get_console(ignore_quiet=True).print(tree)


class SelfPlugin(OPSICLIPlugin):
	name: str = "Self"
	description: str = "Manage opsi-cli"
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
