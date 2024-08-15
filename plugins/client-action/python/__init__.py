"""
opsi-cli basic command line interface for opsi

client-action plugin
"""

import sys

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger

from opsicli.plugin import OPSICLIPlugin

from .client_action_worker import ClientActionArgs
from .execute_worker import ExecuteWorker
from .host_control_worker import HostControlWorker
from .set_action_request_worker import SetActionRequestWorker

__version__ = "0.3.0"
__description__ = "This command can be used to manage opsi client actions."

logger = get_logger("opsicli")


@click.group(name="client-action", short_help="Command group to manage client actions")
@click.version_option(__version__, message="opsi-cli plugin client-action, version %(version)s")
@click.pass_context
@click.option("--clients", help="Comma-separated list of clients or 'all'")
@click.option("--client-groups", help="Comma-separated list of host groups")
@click.option("--clients-from-depots", help="Comma-separated list of depots to get associated clients")
@click.option("--exclude-clients", help="Do not perform actions for these clients")
@click.option("--exclude-client-groups", help="Do not perform actions for these client groups")
@click.option(
	"--only-online",
	help="Limit actions to clients that are connected to the messagebus",
	is_flag=True,
	default=False,
)
@click.option("--ip-addresses", help="Comma-separated list ip addresses or networks")
@click.option(
	"--exclude-ip-addresses",
	help="Comma-separamted list of ip addresses or networks to exclude",
)
def cli(ctx: click.Context, **kwargs: str | bool | None) -> None:
	"""
	This command can be used to manage opsi client actions.
	"""
	logger.trace("client-action command group")
	ctx.obj = ClientActionArgs(**kwargs)  # type: ignore[arg-type]


@cli.command(name="set-action-request", short_help="Set action requests for opsi clients")
@click.pass_context
@click.option(
	"--where-failed",
	help="Set this to add actionRequests for all selected failed products",
	is_flag=True,
	default=False,
)
@click.option(
	"--where-outdated",
	help="Set this to add actionRequests for all selected outdated products",
	is_flag=True,
	default=False,
)
@click.option(
	"--uninstall-where-only-uninstall",
	help="If this is set, any installed package which only has an uninstall script will be set to uninstall",
	is_flag=True,
	default=False,
)
@click.option("--exclude-products", help="Do not set actionRequests for these products")
@click.option("--products", help="Set actionRequests for these products")
@click.option(
	"--product-groups",
	help="Set actionRequests for the products of these product groups",
)
@click.option(
	"--exclude-product-groups",
	help="Do not set actionRequests for these product groups",
)
@click.option(
	"--request-type",
	help="The type of action request to set",
	show_default=True,
	default="setup",
)
@click.option(
	"--setup-on-action",
	help="After actionRequest was set for a client, set these products to setup",
)
def set_action_request(ctx: click.Context, **kwargs: str) -> None:
	"""
	opsi-cli client-action set-action-request command
	"""
	worker = SetActionRequestWorker(ctx.obj)
	worker.set_action_request(**kwargs)


@cli.command(name="trigger-event", short_help="Trigger an event for selected clients")
@click.pass_context
@click.option(
	"--event",
	help="The type of event to trigger",
	show_default=True,
	default="on_demand",
)
@click.option(
	"--wakeup",
	help="Wakeup clients if not online (instead of event trigger)",
	is_flag=True,
	default=False,
)
@click.option(
	"--wakeup-timeout",
	help="Number of seconds to wait for client to wake up (0 = do not wait)",
	type=float,
	default=60.0,
)
def trigger_event(ctx: click.Context, event: str, wakeup: bool, wakeup_timeout: float) -> None:
	"""
	opsi-cli client-action trigger-event command
	"""
	worker = HostControlWorker(ctx.obj)
	worker.trigger_event(event, wakeup, wakeup_timeout=wakeup_timeout)


@cli.command(
	name="execute",
	short_help="Execute a command on selected clients",
	context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False},
)
@click.pass_context
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
@click.option("--timeout", help="Number of seconds until command should be interrupted (0 = no timeout)", type=float, default=0.0)
@click.option("--concurrent", help="Maximum number of concurrent executions", type=int, default=100)
def execute(ctx: click.Context, command: tuple[str], shell: bool, host_names: bool, encoding: str, timeout: float, concurrent: int) -> None:
	"""
	opsi-cli client-action execute command
	"""
	worker = ExecuteWorker(ctx.obj)
	exit_code = worker.execute(command, timeout=timeout, shell=shell, concurrent=concurrent, show_host_names=host_names, encoding=encoding)
	sys.exit(exit_code)


@cli.command(
	name="shutdown",
	short_help="Shutdown selected clients",
	context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False},
)
@click.pass_context
def shutdown(ctx: click.Context) -> None:
	"""
	opsi-cli client-action shutdown clients
	"""
	exit_code = HostControlWorker(ctx.obj).shutdown_clients()
	sys.exit(exit_code)


@cli.command(
	name="wakeup",
	short_help="Wake up selected clients",
	context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False},
)
@click.pass_context
@click.option(
	"--wakeup-timeout",
	help="Number of seconds to wait for client to wake up (0 = do not wait)",
	type=float,
	default=0.0,
)
def wakeup(ctx: click.Context, wakeup_timeout: float) -> None:
	"""
	opsi-cli client-action wake up clients
	"""
	exit_code = HostControlWorker(ctx.obj).wakeup_clients(wakeup_timeout)
	sys.exit(exit_code)


# This class keeps track of the plugins meta-information
class ClientActionPlugin(OPSICLIPlugin):
	name: str = "Client Action"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
