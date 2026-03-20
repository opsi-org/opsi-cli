# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from opsicli.io import Attribute, Metadata

COMMAND_METADATA = {
	"test": Metadata(
		attributes=[
			Attribute(id="depot_id", description="Depot ID", data_type="str"),
			Attribute(id="product_id", description="Product ID", identifier=True, data_type="str"),
			Attribute(id="name", description="Name", data_type="str"),
			Attribute(id="description", description="Description", data_type="str"),
			Attribute(id="product_version", description="Product Version", data_type="str"),
			Attribute(id="package_version", description="Package Version", data_type="str"),
			Attribute(id="product_type", description="Product Type", data_type="str"),
		]
	)
}
