# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli basic command line interface for opsi

This module contains the metadata for the config plugin. The metadata includes information about the subcommands and their attributes.
"""

from opsicli.io import Attribute, Metadata

COMMAND_METADATA = {
	"config_list": Metadata(
		attributes=[
			Attribute(id="name", description="Name of configuration item", identifier=True, data_type="str"),
			Attribute(id="type", description="Data type", data_type="str"),
			Attribute(id="default", description="Default value", data_type="str"),
			Attribute(id="value", description="Current value", data_type="str"),
		]
	),
	"config_show": Metadata(
		attributes=[
			Attribute(id="attribute", description="Name of the configuration item attribute", identifier=True, data_type="str"),
			Attribute(id="value", description="Attribute value", data_type="str"),
		]
	),
	"config_service_list": Metadata(
		attributes=[
			Attribute(id="name", description="The service identifier", identifier=True, data_type="str"),
			Attribute(id="url", description="The base url of the opsi service", data_type="str"),
			Attribute(id="username", description="Username to use for authentication", data_type="str"),
			Attribute(id="password", description="Password to use for authentication", data_type="str"),
			Attribute(id="default", description="Is the default service?", data_type="bool"),
			Attribute(id="session_lifetime", description="The session lifetime in seconds", data_type="int"),
		]
	),
}
