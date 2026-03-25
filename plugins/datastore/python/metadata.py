# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from datetime import datetime, timezone

from opsicommon.types import forceHardwareAddress, forceHostId, forceIpAddress, forceOpsiHostKey, forceOpsiTimestamp, forceUUIDString

from opsicli.io import Attribute, Metadata

CLIENT_METADATA = Metadata(
	attributes=[
		Attribute(
			id="id",
			description="The ID of the client.",
			identifier=True,
			data_type="str",
			selected=True,
			validator=lambda val: forceHostId(val),
		),
		Attribute(
			id="opsiHostKey",
			description="The OPSI host key of the client.",
			identifier=False,
			data_type="str",
			selected=False,
			validator=lambda val: forceOpsiHostKey(val),
		),
		Attribute(
			id="description",
			description="The description of the client.",
			identifier=False,
			data_type="str",
			selected=True,
			validator=lambda val: str(val),
		),
		Attribute(
			id="notes",
			description="The notes of the client.",
			identifier=False,
			data_type="str",
			selected=False,
			validator=lambda val: str(val),
		),
		Attribute(
			id="hardwareAddress",
			description="The hardware address of the client.",
			identifier=False,
			data_type="str",
			selected=False,
			validator=lambda val: forceHardwareAddress(val),
		),
		Attribute(
			id="ipAddress",
			description="The IP address of the client.",
			identifier=False,
			data_type="str",
			selected=False,
			validator=lambda val: forceIpAddress(val),
		),
		Attribute(
			id="inventoryNumber",
			description="The inventory number of the client.",
			identifier=False,
			data_type="str",
			selected=True,
			validator=lambda val: str(val),
		),
		Attribute(
			id="oneTimePassword",
			description="The one time password of the client.",
			identifier=False,
			data_type="str",
			selected=False,
			validator=lambda val: str(val),
		),
		Attribute(
			id="created",
			description="The creation time of the client.",
			identifier=False,
			data_type="datetime",
			selected=False,
			validator=lambda val: forceOpsiTimestamp(datetime.fromisoformat(val).astimezone(timezone.utc).replace(microsecond=0)),
		),
		Attribute(
			id="lastSeen",
			description="The last seen time of the client.",
			identifier=False,
			data_type="datetime",
			selected=True,
			validator=lambda val: forceOpsiTimestamp(datetime.fromisoformat(val).astimezone(timezone.utc).replace(microsecond=0)),
		),
		Attribute(
			id="systemUUID",
			description="The system UUID of the client.",
			identifier=False,
			data_type="str",
			selected=False,
			validator=lambda val: forceUUIDString(val),
		),
	]
)

COMMAND_METADATA = {
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
	"datastore_config-state_update": Metadata(
		attributes=[
			Attribute(id="objectId", description="The ID of the object (host).", identifier=False, data_type="str", selected=True),
			Attribute(id="configId", description="The ID of the config.", identifier=False, data_type="str", selected=True),
			Attribute(
				id="possible",
				description="Possible values of given Config.",
				identifier=False,
				data_type="str | bool",
				selected=True,
			),
			Attribute(
				id="old",
				description="Old values.",
				identifier=False,
				data_type="str | bool",
				selected=True,
			),
			Attribute(
				id="new",
				description="Updated values.",
				identifier=False,
				data_type="str | bool",
				selected=True,
			),
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
	"datastore_client_apply": CLIENT_METADATA,
	"datastore_client_edit": CLIENT_METADATA,
	"datastore_client_list": CLIENT_METADATA,
	"datastore_client_update": CLIENT_METADATA,
}
