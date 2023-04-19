"""
This command can be used to identify potential problems in an opsi environment
"""

from pathlib import Path

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger  # type: ignore[import]

from opsicli.io import Attribute, Metadata, write_output
from opsicli.opsiservice import get_service_connection
from opsicli.plugin import OPSICLIPlugin

from .worker import default_health_check

__version__ = "0.1.0"  # Use this field to track the current version number
__description__ = "This command can be used to identify potential problems in an opsi environment"


logger = get_logger("opsicli")


@click.group(name="support", short_help="Custom plugin support")
@click.version_option(__version__, message="opsi-cli plugin support, version %(version)s")
def cli() -> None:  # The docstring is used in opsi-cli support --help
	""" """
	logger.trace("support command")


@cli.command(short_help="Print server health check")
def health_check() -> None:
	"""
	This command triggers health checks on the server and prints output.
	"""
	metadata = Metadata(
		attributes=[
			Attribute(id="id", description=""),
			Attribute(id="status", description=""),
			Attribute(id="message", description=""),
			Attribute(id="partial_results", description=""),
			Attribute(id="partial_results_status", description=""),
			Attribute(id="partial_results_message", description=""),
		],
	)

	data = default_health_check()

	write_output(data=data, metadata=metadata)


@cli.command(short_help="Get logfile archive from client")
@click.argument("client", type=str)
@click.option("--path", help="Path to put log archive", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), default=Path("."))
def client_logs(client: str, path: Path) -> None:
	"""
	This command instructs an opsi client to pack its logs and deliver them as an archive.
	"""
	service = get_service_connection()
	# instruct client via messagebus to upload its logs and get id
	# request file with id at opsiconfd
	# put file at destination path and print name to console


# This class keeps track of the plugins meta-information
class SupportPlugin(OPSICLIPlugin):
	name: str = "Support"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
