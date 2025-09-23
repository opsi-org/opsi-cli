# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

config-states subcommand
"""

import rich_click as click
from opsicommon.logging import get_logger

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.decorators import dry_run_handling
from opsicli.opsiservice import get_service_connection
from opsicli.plugin import OPSICLIPlugin
from opsicli.rpc_calls import execute_rpc_call

__version__ = "0.1.0"
__description__ = "This command can be used to identify potential problems in an opsi environment"


logger = get_logger("opsicli")


@click.group(cls=OPSICLIGroup, name="config-state", short_help="View configuration states")
@click.version_option(__version__, message="opsi-cli plugin support, version %(version)s")
@click.pass_context
@dry_run_handling(dry_run_capable=True)
def cli(ctx: click.Context, **kwargs: str | bool | None) -> None:
	""" """
	logger.trace("config states command group")


"""
clientconfig.configserver.url ['https://bonifax.uib.local:4447/rpc'] (client)
clientconfig.depot.drive ['p:'] (default)
client1.domain.tld config3 ["5"] (server)
"""


@cli.command(name="list", short_help="List all config states or get a filtered list")
@click.option("--config-id", type=str, default=None)
@click.argument("object_id", type=str, default=None)
def config_states_list(config_id: str | None = None, object_id: str | None = None) -> None:
	"""
	opsi-cli config-state list subcommand.
	"""

	client = get_service_connection()
	default_result = client.config_getObjects(id=config_id or [])
	object_result = client.configState_getObjects(configId=config_id or [], objectId=object_id)
	for entry in default_result:
		if entry.id.startswith("clientconfig"):
			print(entry.id, entry.defaultValues)

	print("----------")
	for entry in object_result:
		if entry.configId.startswith("clientconfig"):
			print(entry.configId, entry.values)

	# wenn client:
	# siehe # opsi-cli jsonrpc execute configState_getClientToDepotserver null nils-client1.uib.local
	# depot_id = execute_rpc_call("configState_getClientToDepotserver", [object_id])
	# depot_result = client.jsonrpc("configState_getObjects", objectId=object_id)


@cli.command(name="create", short_help="Create a config state")
@click.argument("params", type=str, nargs=-1, required=False, default=None)
@click.option("--opt1", type=str, default=None)
@click.option("--opt2", type=str, default=None)
def create_config_state() -> None:
	pass


@cli.command(name="delete", short_help="Delete a config state")
@click.argument("params", type=str, nargs=-1, required=False, default=None)
@click.option("--opt1", type=str, default=None)
@click.option("--opt2", type=str, default=None)
def delete_config_state() -> None:
	pass


class SupportPlugin(OPSICLIPlugin):
	name: str = "Config States"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
