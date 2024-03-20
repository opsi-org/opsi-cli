"""
opsi-cli basic command line interface for opsi

This module contains the metadata for the support plugin. The metadata includes information about the subcommands and their attributes.
"""

from opsicli.io import Attribute, Metadata

command_metadata = {
	"support_health-check": Metadata(
		attributes=[
			Attribute(id="id", description="category of the check - color gives hint of status", data_type="str"),
			Attribute(id="details", description="detailed information of possible problems", data_type="str"),
		],
	)
}
