# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

This module contains the metadata for the package plugin. The metadata includes information about the subcommands and their attributes.
"""

from opsicli.io import Attribute, Metadata

COMMAND_METADATA = {
	"package_list": Metadata(
		attributes=[
			Attribute(id="depot_id", description="Depot ID", data_type="str"),
			Attribute(id="product_id", description="Product ID", identifier=True, data_type="str"),
			Attribute(id="name", description="Name", data_type="str"),
			Attribute(id="description", description="Description", data_type="str"),
			Attribute(id="product_version", description="Product Version", data_type="str"),
			Attribute(id="package_version", description="Package Version", data_type="str"),
			Attribute(id="product_type", description="Product Type", data_type="str"),
		]
	),
	"package_info": Metadata(
		attributes=[
			Attribute(id="package_path", description="The path to the package file.", data_type="str", selected=False),
			Attribute(id="package_filename", description="The filename of the package file.", data_type="str"),
			Attribute(id="product_id", description="The ID of the product.", data_type="str"),
			Attribute(id="product_version", description="The product version of the product.", data_type="str"),
			Attribute(id="package_version", description="The package version of the product.", data_type="str"),
			Attribute(id="product_name", description="The name of the product.", data_type="str"),
			Attribute(id="product_description", description="The description of the product.", data_type="str"),
			Attribute(id="product_advice", description="The advice of the product.", data_type="str", selected=False),
		]
	),
	"package_install": Metadata(
		attributes=[
			Attribute(id="productId", description="Locked product ID", identifier=True, data_type="str"),
			Attribute(id="depotId", description="Depot ID where the product is locked", identifier=True, data_type="str"),
		]
	),
}
