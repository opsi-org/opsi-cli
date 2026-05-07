# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

from opsicli.io import Attribute, Metadata

COMMAND_METADATA = {
	"bootimage_set-boot-password": Metadata(
		attributes=[
			Attribute(id="password_hash", description="The password hash.", data_type="str"),
		]
	)
}
