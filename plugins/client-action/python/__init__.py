"""
opsi-cli basic command line interface for opsi

client-action plugin
"""

import click  # type: ignore[import]
from opsicommon.logging import logger  # type: ignore[import]

from opsicli.plugin import OPSICLIPlugin

from .set_action_request_worker import SetActionRequestWorker

__version__ = "0.1.0"  # Use this field to track the current version number
__description__ = "This command can be used to manage OPSI client actions."


@click.group(name="client-action", short_help="Command group to manage client actions")
@click.version_option(__version__, message="opsi-cli plugin client-action, version %(version)s")
@click.pass_context
@click.option("--clients", help="comma-separated list of clients or 'all'")
@click.option("--client-groups", help="comma-separated list of host groups")
def cli(ctx, clients, client_groups) -> None:
	"""
	This command can be used to manage OPSI client actions.
	"""
	logger.trace("client-action command group")
	ctx.obj = {"clients": clients, "client_groups": client_groups}


@cli.command(name="set-action-request", short_help="Set action requests for OPSI clients")
@click.pass_context
@click.option("--where-failed", help="Set this to add actionRequests for all selected failed products", is_flag=True, default=False)
@click.option("--where-outdated", help="Set this to add actionRequests for all selected outdated products", is_flag=True, default=False)
@click.option(
	"--uninstall-where-only-uninstall",
	help="If this is set, any installed package which only has an uninstall script will be set to uninstall",
	is_flag=True,
	default=False,
)
@click.option("--exclude-products", help="do not set actionRequests for these products")
@click.option("--include-products", help="set actionRequests ONLY for these products")
@click.option("--request-type", help="The type of action request to set", show_default=True, default="setup")
def set_action_request(ctx, **kwargs) -> None:
	"""
	opsi-cli client-action set-action-request command
	"""
	kwargs.update(ctx.obj)
	worker = SetActionRequestWorker(**kwargs)
	worker.set_action_request(
		where_failed=kwargs["where_failed"],
		where_outdated=kwargs["where_outdated"],
		uninstall_where_only_uninstall=kwargs["uninstall_where_only_uninstall"]
	)


# This class keeps track of the plugins meta-information
class ClientActionPlugin(OPSICLIPlugin):
	id: str = "client-action"  # pylint: disable=invalid-name
	name: str = "Client Action"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = []
