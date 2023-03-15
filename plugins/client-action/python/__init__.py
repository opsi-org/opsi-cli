"""
opsi-cli basic command line interface for opsi

client-action plugin
"""

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli.plugin import OPSICLIPlugin

from .set_action_request_worker import SetActionRequestWorker

__version__ = "0.1.0"  # Use this field to track the current version number
__description__ = "This command can be used to manage opsi client actions."

logger = get_logger("opsicli")


@click.group(name="client-action", short_help="Command group to manage client actions")
@click.version_option(__version__, message="opsi-cli plugin client-action, version %(version)s")
@click.pass_context
@click.option("--clients", help="Comma-separated list of clients or 'all'")
@click.option("--client-groups", help="Comma-separated list of host groups")
@click.option("--exclude-clients", help="Do not perform actions for these clients")
@click.option("--exclude-client-groups", help="Do not perform actions for these client groups")
def cli(ctx: click.Context, clients: str, client_groups: str, exclude_clients: str, exclude_client_groups: str) -> None:
	"""
	This command can be used to manage opsi client actions.
	"""
	logger.trace("client-action command group")
	ctx.obj = {
		"clients": clients,
		"client_groups": client_groups,
		"exclude_clients": exclude_clients,
		"exclude_client_groups": exclude_client_groups
	}


@cli.command(name="set-action-request", short_help="Set action requests for opsi clients")
@click.pass_context
@click.option("--where-failed", help="Set this to add actionRequests for all selected failed products", is_flag=True, default=False)
@click.option("--where-outdated", help="Set this to add actionRequests for all selected outdated products", is_flag=True, default=False)
@click.option(
	"--uninstall-where-only-uninstall",
	help="If this is set, any installed package which only has an uninstall script will be set to uninstall",
	is_flag=True,
	default=False,
)
@click.option("--exclude-products", help="Do not set actionRequests for these products")
@click.option("--products", help="Set actionRequests for these products")
@click.option("--product-groups", help="Set actionRequests for the products of these product groups")
@click.option("--exclude-product-groups", help="Do not set actionRequests for these product groups")
@click.option("--request-type", help="The type of action request to set", show_default=True, default="setup")
@click.option("--setup-on-action", help="After actionRequest was set for a client, set these products to setup")
def set_action_request(ctx: click.Context, **kwargs: str) -> None:
	"""
	opsi-cli client-action set-action-request command
	"""
	worker = SetActionRequestWorker(**ctx.obj)
	worker.set_action_request(**kwargs)


# This class keeps track of the plugins meta-information
class ClientActionPlugin(OPSICLIPlugin):
	name: str = "Client Action"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
