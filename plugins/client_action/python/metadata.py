# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from opsicli.io import Attribute, Metadata

COMMAND_METADATA = {
	"client-action_set-action-request": Metadata(
		attributes=[
			Attribute(id="clientId", description="ID of the client", identifier=True, data_type="str"),
			Attribute(id="productId", description="ID of the product", identifier=True, data_type="str"),
			Attribute(id="actionRequest", description="Product action request set", data_type="str"),
			Attribute(id="actionProgress", description="Product action progress", data_type="str", selected=False),
			Attribute(id="actionResult", description="Product action result", data_type="str", selected=False),
			Attribute(id="installationStatus", description="Product installation status", data_type="str", selected=False),
		]
	)
}
