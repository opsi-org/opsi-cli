"""
opsi-cli basic command line interface for opsi

This module contains the metadata for the package plugin. The metadata includes information about the subcommands and their attributes.
"""

from opsicli.io import Attribute, Metadata

command_metadata = {
	"package_list": Metadata(
		attributes=[
			Attribute(id="depot_id", description="Depot ID", data_type="str"),
			Attribute(id="product_id", description="Product ID", identifier=True, data_type="str"),
			Attribute(id="name", description="Name", data_type="str"),
			Attribute(id="description", description="Description", data_type="str"),
			Attribute(id="product_version", description="Product Version", data_type="str"),
			Attribute(id="package_version", description="Package Version", data_type="str"),
		]
	)
}
