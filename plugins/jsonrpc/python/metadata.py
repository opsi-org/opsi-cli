"""
opsi-cli basic command line interface for opsi

This module contains the metadata for the jsonrpc plugin. The metadata includes information about the subcommands and their attributes.
"""

from opsicli.io import Attribute, Metadata

command_metadata = {
	"methods": Metadata(
		attributes=[
			Attribute(id="name", description="Method name", identifier=True, data_type="string"),
			Attribute(id="params", description="Method params", data_type="string"),
			Attribute(id="deprecated", description="If the method is deprectated", data_type="bool"),
			Attribute(id="alternative_method", description="Alternative method, if deprecated", data_type="string"),
			Attribute(id="args", description="Args", selected=False),
			Attribute(id="varargs", description="Varargs", selected=False),
			Attribute(id="keywords", description="Keywords", selected=False),
			Attribute(id="defaults", description="Defaults", selected=False),
		]
	)
}
