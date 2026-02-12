from opsicli.io import Attribute, Metadata

command_metadata = {
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
