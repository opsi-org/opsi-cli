# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from dataclasses import replace
from datetime import datetime, timezone

from opsi.opsi.service.model.type import (
	to_bool,
	to_config_id,
	to_hardware_address,
	to_host_id,
	to_ip_address,
	to_object_id,
	to_opsi_host_key,
	to_opsi_timestamp,
	to_package_version,
	to_product_id,
	to_product_property_id,
	to_product_version,
	to_uuid_string,
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
			validator=lambda val: to_host_id(val),
		),
		Attribute(
			id="opsiHostKey",
			description="The OPSI host key of the client.",
			identifier=False,
			data_type="str",
			selected=False,
			validator=lambda val: to_opsi_host_key(val),
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
			validator=lambda val: to_hardware_address(val),
		),
		Attribute(
			id="ipAddress",
			description="The IP address of the client.",
			identifier=False,
			data_type="str",
			selected=False,
			validator=lambda val: to_ip_address(val),
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
			validator=lambda val: to_opsi_timestamp(datetime.fromisoformat(val).astimezone(timezone.utc).replace(microsecond=0)),
		),
		Attribute(
			id="lastSeen",
			description="The last seen time of the client.",
			identifier=False,
			data_type="datetime",
			selected=True,
			validator=lambda val: to_opsi_timestamp(datetime.fromisoformat(val).astimezone(timezone.utc).replace(microsecond=0)),
		),
		Attribute(
			id="systemUUID",
			description="The system UUID of the client.",
			identifier=False,
			data_type="str",
			selected=False,
			validator=lambda val: to_uuid_string(val),
		),
	]
)

object_id = Attribute(
	id="objectId",
	description="The ID of the object.",
	identifier=True,
	data_type="str",
	selected=True,
	validator=lambda val: to_object_id(val),
)
config_id = Attribute(
	id="configId",
	description="The ID of the config.",
	identifier=True,
	data_type="str",
	selected=True,
	validator=lambda val: to_config_id(val),
)
description = Attribute(
	id="description",
	description="The description of the state.",
	identifier=False,
	data_type="str",
	selected=False,
	validator=lambda val: str(val),
)
multi_value = Attribute(
	id="multiValue",
	description="Indicates if given state accepts multi-values.",
	identifier=False,
	data_type="bool",
	selected=False,
	validator=lambda val: to_bool(val),
)
editable = Attribute(
	id="editable",
	description="Indicates if given state is editable.",
	identifier=False,
	data_type="bool",
	selected=False,
	validator=lambda val: to_bool(val),
)
values = Attribute(
	id="values",
	description="The current effective value for this state.",
	identifier=False,
	data_type="str | bool",
	selected=True,
)
possible_values = Attribute(
	id="possibleValues",
	description="Possible values of the state.",
	identifier=False,
	data_type="str | bool",
	selected=False,
)
default_values = Attribute(
	id="defaultValues",
	description="Default values of the state.",
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
	description="Depot values of the state.",
	identifier=False,
	data_type="str | bool",
	selected=False,
)
client_values = Attribute(
	id="clientValues",
	description="Client values of the state.",
	identifier=False,
	data_type="str | bool",
	selected=False,
)
origin = Attribute(id="origin", description="Location where the change has been made.", identifier=False, data_type="str", selected=True)
previous_values = Attribute(
	id="previousValues",
	description="Values before change.",
	identifier=False,
	data_type="str | bool",
	selected=True,
)
product_id = Attribute(
	id="productId",
	description="The ID of the product.",
	identifier=True,
	data_type="str",
	selected=True,
	validator=lambda val: to_product_id(val),
)
property_id = Attribute(
	id="propertyId",
	description="The ID of the property.",
	identifier=True,
	data_type="str",
	selected=True,
	validator=lambda val: to_product_property_id(val),
)
product_version = Attribute(
	id="productVersion",
	description="The product version of the state.",
	identifier=False,
	data_type="str",
	selected=False,
	validator=lambda val: to_product_version(val),
)
package_version = Attribute(
	id="packageVersion",
	description="The package version of the state.",
	identifier=False,
	data_type="str",
	selected=False,
	validator=lambda val: to_package_version(val),
)
is_default = Attribute(
	id="isDefault",
	description="Indicates if values are default.",
	identifier=False,
	data_type="str",
	selected=False,
	validator=lambda val: to_bool(val),
)
depot_id = Attribute(
	id="depotId",
	description="The ID of the depotserver.",
	identifier=False,
	data_type="str",
	selected=False,
	validator=lambda val: to_object_id(val),
)
client_id = Attribute(id="clientId", description="The ID of the client.", identifier=True, data_type="str", selected=True)
product_type = Attribute(id="productType", description="The type of the product.", identifier=True, data_type="str", selected=True)
installation_status = Attribute(
	id="installationStatus",
	description="The installation status of the product.",
	identifier=False,
	data_type="str",
	selected=True,
)
action_request = Attribute(
	id="actionRequest", description="The action request of the product.", identifier=False, data_type="str", selected=True
)
modification_time = Attribute(
	id="modificationTime",
	description="The last modification time of the product state.",
	identifier=False,
	data_type="datetime",
	selected=True,
)


COMMAND_METADATA = {
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
			depot_id,
		]
	),
	"datastore_config-state_update": Metadata(attributes=[object_id, config_id, possible_values, previous_values, values]),
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
			depot_id,
		]
	),
	"datastore_product-client-state_list": Metadata(
		attributes=[
			client_id,
			product_id,
			product_type,
			replace(product_version, selected=True),
			replace(package_version, selected=True),
			installation_status,
			action_request,
			modification_time,
		]
	),
	"datastore_product_unlock": Metadata(attributes=[product_id, replace(depot_id, identifier=True)]),
	"datastore_product_purge": Metadata(attributes=[product_id]),
	"datastore_client_apply": CLIENT_METADATA,
	"datastore_client_edit": CLIENT_METADATA,
	"datastore_client_list": CLIENT_METADATA,
	"datastore_client_update": CLIENT_METADATA,
}
