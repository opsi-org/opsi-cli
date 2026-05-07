# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

This module contains the metadata for the support plugin. The metadata includes information about the subcommands and their attributes.
"""

from opsicli.io import Attribute, Metadata

COMMAND_METADATA = {
	"support_health-check": Metadata(
		attributes=[
			Attribute(id="id", description="category of the check - color gives hint of status", data_type="str"),
			Attribute(id="details", description="detailed information of possible problems", data_type="str"),
		],
	)
}
