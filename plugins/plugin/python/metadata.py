"""
opsi-cli basic command line interface for opsi

This module contains the metadata for the plugin subcommand. The metadata includes information about the subcommands and their attributes.
"""

from opsicli.io import Attribute, Metadata

command_metadata = {
	"list": Metadata(
		attributes=[
			Attribute(id="id", description="Plugin ID", identifier=True, data_type="str"),
			Attribute(id="name", description="Name of the Plugin", data_type="str"),
			Attribute(id="description", description="Plugin description", data_type="str"),
			Attribute(id="version", description="Version of the plugin", data_type="str"),
			Attribute(id="path", description="Location of the plugin", data_type="str"),
		]
	)
}
