# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

This module contains the metadata for the jsonrpc plugin. The metadata includes information about the subcommands and their attributes.
"""

from opsicli.io import Attribute, Metadata

command_metadata = {
	"datastore_config-state_list": Metadata(
		attributes=[
			Attribute(id="objectId", description="The ID of the object (host).", identifier=False, data_type="str", selected=True),
			Attribute(id="configId", description="The ID of the config.", identifier=False, data_type="str", selected=True),
			Attribute(
				id="default_values",
				description="Values of given Config.",
				identifier=False,
				data_type="str | bool",
				selected=False,
			),
			Attribute(
				id="depot_values",
				description="Values of given config state.",
				identifier=False,
				data_type="str | bool",
				selected=False,
			),
			Attribute(
				id="client_values",
				description="Values of given config state.",
				identifier=False,
				data_type="str | bool",
				selected=False,
			),
			Attribute(
				id="final_values",
				description="Values of given config state.",
				identifier=False,
				data_type="str | bool",
				selected=True,
				column_style="green",
			),
			Attribute(id="origin", description="Location where the change was made.", identifier=False, data_type="str", selected=True),
		]
	),
	"datastore_product-property-state_list": Metadata(
		attributes=[
			Attribute(id="objectId", description="The ID of the object.", identifier=False, data_type="str", selected=True),
			Attribute(id="productId", description="The ID of the product.", identifier=False, data_type="str", selected=True),
			Attribute(id="propertyId", description="The ID of the property.", identifier=False, data_type="str", selected=True),
			Attribute(
				id="default_values",
				description="Values of given property.",
				identifier=False,
				data_type="str | bool",
				selected=False,
			),
			Attribute(id="depot_values", description="Values of given property.", identifier=False, data_type="str | bool", selected=False),
			Attribute(
				id="client_values", description="Values of given property.", identifier=False, data_type="str | bool", selected=False
			),
			Attribute(
				id="final_values",
				description="Values of given property.",
				identifier=False,
				data_type="str | bool",
				selected=True,
				column_style="green",
			),
			Attribute(
				id="origin",
				description="Location where the change was made.",
				identifier=False,
				data_type="str",
				selected=True,
			),
		]
	),
	"datastore_product-client-state_list": Metadata(
		attributes=[
			Attribute(id="clientId", description="The ID of the client.", identifier=True, data_type="str", selected=True),
			Attribute(id="productId", description="The ID of the product.", identifier=True, data_type="str", selected=True),
			Attribute(id="productType", description="The type of the product.", identifier=True, data_type="str", selected=True),
			Attribute(id="productVersion", description="The installed product version.", identifier=False, data_type="str", selected=True),
			Attribute(id="packageVersion", description="The installed package version.", identifier=False, data_type="str", selected=True),
			Attribute(
				id="installationStatus",
				description="The installation status of the product.",
				identifier=False,
				data_type="str",
				selected=True,
			),
			Attribute(
				id="actionRequest", description="The action request of the product.", identifier=False, data_type="str", selected=True
			),
			Attribute(
				id="modificationTime",
				description="The last modification time of the product state.",
				identifier=False,
				data_type="datetime",
				selected=True,
			),
		]
	),
	"datastore_client_list": Metadata(
		attributes=[
			Attribute(id="id", description="The ID of the client.", identifier=True, data_type="str", selected=True),
			Attribute(id="opsiHostKey", description="The OPSI host key of the client.", identifier=False, data_type="str", selected=False),
			Attribute(id="description", description="The description of the client.", identifier=False, data_type="str", selected=True),
			Attribute(id="notes", description="The notes of the client.", identifier=False, data_type="str", selected=False),
			Attribute(
				id="hardwareAddress", description="The hardware address of the client.", identifier=False, data_type="str", selected=False
			),
			Attribute(id="ipAddress", description="The IP address of the client.", identifier=False, data_type="str", selected=False),
			Attribute(
				id="inventoryNumber", description="The inventory number of the client.", identifier=False, data_type="str", selected=True
			),
			Attribute(
				id="oneTimePassword", description="The one time password of the client.", identifier=False, data_type="str", selected=False
			),
			Attribute(id="created", description="The creation time of the client.", identifier=False, data_type="datetime", selected=False),
			Attribute(
				id="lastSeen", description="The last seen time of the client.", identifier=False, data_type="datetime", selected=True
			),
			Attribute(id="systemUUID", description="The system UUID of the client.", identifier=False, data_type="str", selected=False),
		]
	),
}
