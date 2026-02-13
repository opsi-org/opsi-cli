from opsicli.io import Attribute, Metadata

command_metadata = {
	"bootimage_set-boot-password": Metadata(
		attributes=[
			Attribute(id="password_hash", description="The password hash.", data_type="str"),
		]
	)
}
