# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only
from datetime import datetime, timezone

from opsicommon.types import (
	forceHardwareAddress,
	forceHostId,
	forceIpAddress,
	forceOpsiHostKey,
	forceOpsiTimestamp,
	forceUUIDString,
)

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

object_id = Attribute(
	id="objectId",
	description="The ID of the object (host).",
	identifier=True,
	data_type="str",
	selected=False,
)
config_id = Attribute(
	id="configId",
	description="The ID of the config-state.",
	identifier=True,
	data_type="str",
	selected=False,
)
description = Attribute(
	id="description",
	description="The description of given state.",
	identifier=False,
	data_type="str",
	selected=False,
)
multi_value = Attribute(
	id="multiValue",
	description="Shows if given state accepts multi-values.",
	identifier=False,
	data_type="str",
	selected=False,
)
editable = Attribute(
	id="editable",
	description="Shows if given state is editable via configed.",
	identifier=False,
	data_type="str",
	selected=False,
)
values = Attribute(
	id="values",
	description="The current effective value for this state.",
	identifier=False,
	data_type="str | bool",
	selected=False,
)
possible_values = Attribute(
	id="possibleValues",
	description="Possible values of given state.",
	identifier=False,
	data_type="str | bool",
	selected=False,
)
default_values = Attribute(
	id="defaultValues",
	description="Default values of given state.",
	identifier=False,
	data_type="str | bool",
	selected=False,
)
type = Attribute(
	id="type",
	description="The type of the state object. (Bool/Unicode)",
	identifier=False,
	data_type="str | bool",
	selected=False,
)
depot_values = Attribute(
	id="depotValues",
	description="Depot values of given state.",
	identifier=False,
	data_type="str | bool",
	selected=False,
)
client_values = Attribute(
	id="clientValues",
	description="Client values of given state.",
	identifier=False,
	data_type="str | bool",
	selected=False,
)
origin = Attribute(id="origin", description="Location where the change has been made.", identifier=False, data_type="str", selected=False)
old = Attribute(
	id="old",
	description="Old values.",
	identifier=False,
	data_type="str | bool",
	selected=False,
)
new = Attribute(
	id="new",
	description="New values.",
	identifier=False,
	data_type="str | bool",
	selected=False,
)
product_id = Attribute(id="productId", description="The ID of the product.", identifier=True, data_type="str", selected=False)
property_id = Attribute(id="propertyId", description="The ID of the property.", identifier=True, data_type="str", selected=False)
product_version = Attribute(
	id="productVersion", description="The product version of given state.", identifier=False, data_type="str", selected=False
)
package_version = Attribute(
	id="packageVersion", description="The package version of given state.", identifier=False, data_type="str", selected=False
)
is_default = Attribute(id="Indicates if values are default.", identifier=False, data_type="str", selected=False)

COMMAND_METADATA = {
	"set": Metadata(attributes=[values]),
	"datastore_config-state_list": Metadata(
		attributes=[
			object_id,
			config_id,
			description,
			multi_value,
			editable,
			values,
			possible_values,
			default_values,
			depot_values,
			client_values,
			origin,
		]
	),
	"datastore_config-state_update": Metadata(attributes=[object_id, config_id, possible_values, old, new]),
	"datastore_product-property-state_list": Metadata(
		attributes=[
			object_id,
			product_id,
			property_id,
			product_version,
			package_version,
			type,
			description,
			editable,
			multi_value,
			values,
			is_default,
			default_values,
			depot_values,
			client_values,
			origin,
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
