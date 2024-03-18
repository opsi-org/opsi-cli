"""
opsi-cli depot plugin
"""

import sys

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger

from opsicli.plugin import OPSICLIPlugin

from .depot_execute_worker import DepotExecuteWorker

__version__ = "0.1.0"  # Use this field to track the current version number
__description__ = "plugin for controlling opsi depots"


logger = get_logger("opsicli")


@click.group(name="depot", short_help="plugin for controlling opsi depots")
@click.version_option(__version__, message="opsi-cli plugin depot, version %(version)s")
@click.option("--depots", help="comma separated list of depots, or 'all'")
@click.pass_context
def cli(ctx: click.Context, depots: str | None) -> None:  # The docstring is used in opsi-cli depot --help
	"""
	plugin for controlling opsi depots
	"""
	logger.trace("depot command")
	ctx.obj = {"depots": depots}


@cli.command(short_help="let depot(s) execute a command")
@click.argument("command", nargs=-1, required=True)
@click.option("--shell", help="Execute command in a shell", is_flag=True, default=False)
@click.option("--host-names/--no-host-names", help="Prepend the host name on output", is_flag=True, default=True)
@click.option(
	"--encoding",
	help=(
		"Encoding to be used for decoding incoming data. "
		"'auto' automatically attempts to find the correct encoding (default). "
		"'raw' does not decode the data at all."
	),
	type=str,
	default="auto",
)
@click.option("--timeout", help="Number of seconds until command should be interrupted (0 = no timeout)", type=int, default=0)
@click.option("--concurrent", help="Maximum number of concurrent executions", type=int, default=100)
@click.pass_context
def execute(ctx: click.Context, command: tuple[str], shell: bool, host_names: bool, encoding: str, timeout: int, concurrent: int) -> None:
	"""
	opsi-cli depot execute command
	"""
	worker = DepotExecuteWorker(ctx.obj.get("depots"))
	exit_code = worker.execute(command, timeout=timeout, shell=shell, concurrent=concurrent, show_host_names=host_names, encoding=encoding)
	sys.exit(exit_code)


# This class keeps track of the plugins meta-information
class CustomPlugin(OPSICLIPlugin):
	name: str = "depot"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = []
