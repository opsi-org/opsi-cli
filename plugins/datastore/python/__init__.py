# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from opsicli.plugin import OPSICLIPlugin

from . import (
	client,  # noqa: F401
	config_state,  # noqa: F401
	product,  # noqa: F401
	product_client_state,  # noqa: F401
	product_property_state,  # noqa: F401
)
from .common import __description__, __version__, cli


class DatastorePlugin(OPSICLIPlugin):
	name: str = "Datastore"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = ["protected"]
