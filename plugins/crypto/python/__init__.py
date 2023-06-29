"""
opsi-cli crypto
"""

import passlib.hash  # type: ignore[import]
import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger

from opsicli.plugin import OPSICLIPlugin

__version__ = "0.1.0"  # Use this field to track the current version number
__description__ = "cryptography functions"


logger = get_logger("opsicli")


@click.group(name="crypto", short_help="Custom plugin crypto")
@click.version_option(__version__, message="opsi-cli plugin crypto, version %(version)s")
def cli() -> None:  # The docstring is used in opsi-cli crypto --help
	"""
	cryptography functions
	"""
	logger.trace("crypto command")


@cli.command(short_help="convert cleartext password to a hash")
@click.argument("cleartext_password", nargs=1, default="linux123", type=str)
def password_to_hash(cleartext_password: str) -> None:  # create a password hash from a cleartext password
	while True:
		hashed_password = passlib.hash.sha512_crypt.encrypt(cleartext_password)
		if not hashed_password or "." in hashed_password:
			logger.warning("invalid hash. trying again")
		else:
			print(f"password hash is: {hashed_password}")
			print(f"opsi-linux-bootimage.append parameter is: 'pwh={hashed_password}'")
			break


# This class keeps track of the plugins meta-information
class CustomPlugin(OPSICLIPlugin):
	name: str = "crypto"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = []
