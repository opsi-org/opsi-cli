# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

client-action plugin
"""

import sys

import rich_click as click
from opsicommon.logging import get_logger

from opsicli.decorators import dry_run_handling
from opsicli.io import deprecation_warning
from opsicli.plugin import OPSICLIPlugin

from .client_action_worker import ClientActionArgs
from .execute_worker import ExecuteWorker
from .host_control_worker import HostControlWorker
from .set_action_request_worker import SetActionRequestArgs, SetActionRequestWorker

__version__ = "0.3.0"
__description__ = "This command can be used to manage opsi client actions."

logger = get_logger("opsicli")


@click.group(name="client-action", short_help="Command group to manage client actions")
@click.version_option(__version__, message="opsi-cli plugin client-action, version %(version)s")
@click.pass_context
@click.option("--clients", help="Select clients IDs (comma-separated list) or use 'all' for all clients.")
@click.option("--client-groups", help="Select clients from these client groups (comma-separated list).")
@click.option("--clients-from-depots", help="Select clients from these depots.")
@click.option("--exclude-clients", help="Exclude these clients IDs (comma-separated list).")
@click.option("--exclude-client-groups", help="Do not perform actions for these client groups (comma-separated list).")
@click.option(
	"--only-online",
	help="Limit actions to clients that are connected to the messagebus.",
	is_flag=True,
	default=False,
)
@click.option("--ip-addresses", help="Select clients by IP addresses or networks (comma-separated list).")
@click.option(
	"--exclude-ip-addresses",
	help="Exclude clients by IP addresses or networks (comma-separated list).",
)
@dry_run_handling()
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
	help="Set this to add actionRequests where the selected products failed.",
	is_flag=True,
	default=False,
)
@click.option(
	"--where-outdated",
	help="Set this to add actionRequests where the selected products are outdated.",
	is_flag=True,
	default=False,
)
@click.option(
	"--where-installed",
	help="Set this to add actionRequests where the selected products are installed.",
	is_flag=True,
	default=False,
)
@click.option(
	"--uninstall-where-only-uninstall",
	help="If this is set, any installed package which only has an uninstall script will be set to uninstall.",
	is_flag=True,
	default=False,
)
@click.option(
	"--exclude-products",
	help="Do not set actionRequests for these products (comma-separated list).",
)
@click.option(
	"--products",
	help="Set actionRequests for these products (comma-separated list).",
)
@click.option(
	"--product-groups",
	help="Set actionRequests for the products of these product groups (comma-separated list).",
)
@click.option(
	"--exclude-product-groups",
	help="Do not set actionRequests for these product groups (comma-separated list).",
)
@click.option(
	"--request-type",
	help="Deprecated, please use `--set-action-request`.",
	show_default=False,
	default=None,
	hidden=True,
)
@click.option(
	"--set-action-request",
	help="The action request to set.",
	show_default=True,
	default="setup",
)
@click.option(
	"--set-action-progress",
	help="The action progress to set.",
	show_default=True,
	default=None,
)
@click.option(
	"--set-action-result",
	help="The action result to set.",
	show_default=True,
	default=None,
)
@click.option(
	"--set-installation-status",
	help="The action progress to set.",
	show_default=True,
	default=None,
)
@click.option(
	"--setup-on-action",
	help="If an actionRequest has been set for a client, also set these products to setup (comma-separated list).",
)
@click.option(
	"--process",
	help="Process the action requests immediately.",
	is_flag=True,
	default=False,
)
@click.option(
	"--process-visibility",
	type=click.Choice(["visible", "hidden"], case_sensitive=False),
	help="The visibility of action processing on the client. Client default, if not specified.",
	default=None,
)
@dry_run_handling(dry_run_capable=True)
def set_action_request(ctx: click.Context, **kwargs: str | bool) -> None:
	"""
	opsi-cli client-action set-action-request command
	"""
	worker = SetActionRequestWorker(ctx.obj)

	request_type = kwargs.pop("request_type", None)
	if request_type:
		deprecation_warning("The `--request-type` option is deprecated, please use `--set-action-request` instead.\n")
		kwargs["set_action_request"] = request_type

	worker.set_action_request(SetActionRequestArgs(**kwargs))  # type: ignore[arg-type]


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
@dry_run_handling(dry_run_capable=True)
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
@click.argument("command", nargs=-1)
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
@click.option(
	"--opsi-script",
	help=(
		"Provide the content of an opsi-script directly. "
		"No command is needed when using this option. "
		"Use --opsi-script-log-level to filter logs in the execution summary."
	),
	type=str,
)
@click.option(
	"--opsi-script-log-level",
	type=click.IntRange(1, 8),
	default=4,
	help="Specify the log level to filter (1 to 8). Only available with --opsi-script",
	show_default=True,
)
@dry_run_handling(dry_run_capable=True)
def execute(
	ctx: click.Context,
	command: tuple[str],
	shell: bool,
	host_names: bool,
	encoding: str,
	timeout: float,
	concurrent: int,
	opsi_script: str,
	opsi_script_log_level: int,
) -> None:
	"""
	Executes a command or opsi-script on selected clients.
	"""
	if not command and not opsi_script:
		raise click.UsageError("Missing argument 'COMMAND...' or '--opsi-script' option.")

	if opsi_script:
		try:
			opsi_script.encode("utf-8", errors="strict")
		except UnicodeEncodeError:
			raise ValueError("The opsi-script content is not valid UTF-8")

	worker = ExecuteWorker(ctx.obj)
	exit_code = worker.execute(
		command,
		timeout=timeout,
		shell=shell,
		concurrent=concurrent,
		show_host_names=host_names,
		encoding=encoding,
		opsiscript=opsi_script,
		opsiscript_log_level=opsi_script_log_level,
	)
	sys.exit(exit_code)


@cli.command(
	name="shutdown",
	short_help="Shutdown selected clients",
	context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False},
)
@click.pass_context
@dry_run_handling(dry_run_capable=True)
def shutdown(ctx: click.Context) -> None:
	"""
	opsi-cli client-action shutdown clients
	"""
	HostControlWorker(ctx.obj).shutdown_clients()


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
@dry_run_handling(dry_run_capable=True)
def wakeup(ctx: click.Context, wakeup_timeout: float) -> None:
	"""
	opsi-cli client-action wake up clients
	"""
	HostControlWorker(ctx.obj).wakeup_clients(wakeup_timeout)


# This class keeps track of the plugins meta-information
class ClientActionPlugin(OPSICLIPlugin):
	name: str = "Client Action"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
