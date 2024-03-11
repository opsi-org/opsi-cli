"""
opsi-cli basic command line interface for opsi

This module contains the metadata for the config plugin. The metadata includes information about the subcommands and their attributes.
"""

from opsicli.io import Attribute, Metadata

command_metadata = {
	"list": Metadata(
		attributes=[
			Attribute(id="name", description="Name of configuration item", identifier=True, data_type="str"),
			Attribute(id="type", description="Data type", data_type="str"),
			Attribute(id="default", description="Default value", data_type="str"),
			Attribute(id="value", description="Current value", data_type="str"),
		]
	),
	"show": Metadata(
		attributes=[
			Attribute(id="attribute", description="Name of the configuration item attribute", identifier=True, data_type="str"),
			Attribute(id="value", description="Attribute value", data_type="str"),
		]
	),
	"service_list": Metadata(
		attributes=[
			Attribute(id="name", description="The service identifier", identifier=True, data_type="str"),
			Attribute(id="url", description="The base url of the opsi service", data_type="str"),
			Attribute(id="username", description="Username to use for authentication", data_type="str"),
			Attribute(id="password", description="Password to use for authentication", data_type="str"),
		]
	),
}
