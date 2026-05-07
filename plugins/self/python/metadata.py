# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from opsicli.io import Attribute, Metadata

COMMAND_METADATA = {
	"self_installed-versions": Metadata(
		attributes=[
			Attribute(id="path", description="Location of the binary", identifier=True, data_type="str"),
			Attribute(id="version", description="Version of the binary", data_type="str"),
			Attribute(
				id="in_path",
				description="Is the binary file located in a directory that is contained in the PATH environment variable?",
				data_type="bool",
			),
			Attribute(id="default", description="Default binary (first in PATH)?", data_type="bool"),
			Attribute(id="writable", description="Is the binary writable?", data_type="bool"),
		]
	)
}
