# metadata.py

from opsicli.io import Attribute, Metadata

command_metadata = {
	"list": Metadata(
		attributes=[
			Attribute(id="name", description="Name of configuration item", identifier=True, type="string"),
			Attribute(id="type", description="Data type", type="string"),
			Attribute(id="default", description="Default value", type="string"),
			Attribute(id="value", description="Current value", type="string"),
		]
	),
	"show": Metadata(
		attributes=[
			Attribute(id="attribute", description="Name of the configuration item attribute", identifier=True, type="string"),
			Attribute(id="value", description="Attribute value", type="string"),
		]
	),
	"service_list": Metadata(
		attributes=[
			Attribute(id="name", description="The service identifier", identifier=True, type="string"),
			Attribute(id="url", description="The base url of the opsi service", type="string"),
			Attribute(id="username", description="Username to use for authentication", type="string"),
			Attribute(id="password", description="Password to use for authentication", type="string"),
		]
	),
}
