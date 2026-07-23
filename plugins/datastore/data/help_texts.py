from dataclasses import dataclass


@dataclass(frozen=True)
class HelpTexts:
	short: str | None = None
	long: str | None = None
	where: str | None = None
	all: str | None = None
	set: str | None = None


@dataclass(frozen=True)
class CommandHelp:
	APPLY: HelpTexts = HelpTexts()
	DELETE: HelpTexts = HelpTexts()
	EDIT: HelpTexts = HelpTexts()
	GENERAL: HelpTexts = HelpTexts()
	LIST: HelpTexts = HelpTexts()
	PURGE: HelpTexts = HelpTexts()
	UPDATE: HelpTexts = HelpTexts()
	UNLOCK: HelpTexts = HelpTexts()


# HINT: Not yet implemented operations are commented out
CLIENT_HELP = CommandHelp(
	APPLY=HelpTexts(
		short="Bulk import or modify clients.",
		long=(
			"Create or update client hosts by piping JSON/YAML data via stdin or '--input-file'.\n\n"
			"[bold]Examples:[/]\n"
			"cat clients.json | opsi-cli datastore client apply\n"
			"opsi-cli datastore client apply --input-file clients.yaml"
		),
	),
	# DELETE=HelpTexts(),
	EDIT=HelpTexts(
		short="Edit client attributes in a terminal editor.",
		long=(
			"Fetch client definitions and open them in your default system text editor. Saving the file applies changes to the OPSI database.\n\n"
			"[bold]Examples:[/]\n"
			"opsi-cli datastore client edit --where 'id=win10-*'"
		),
		where="Filter clients to edit (e.g., --where 'id=win10-*').",
	),
	GENERAL=HelpTexts(
		short="Manage OPSI clients.",
		long="View, modify, or add client host records in the OPSI backend database.",
	),
	LIST=HelpTexts(
		short="List registered OPSI clients.",
		long=(
			"Display OPSI client host records from the datastore.\n\n"
			"[bold]Examples:[/]\n"
			"opsi-cli datastore client list --where 'id=*.domain.local'\n"
			"opsi-cli datastore client list --all"
		),
		where="Filter by host fields (e.g., --where 'ipAddress=192.168.1.*').",
		all="Show all records, ignoring filters.",
	),
	UPDATE=HelpTexts(
		short="Modify host fields on clients.",
		long=(
			"Update backend parameters directly on targeted OPSI clients.\n\n"
			"[bold]Examples:[/]\n"
			"opsi-cli datastore client update --where 'id=test.local' --set 'notes=Assigned'\n"
			"opsi-cli datastore client update --where 'hardwareAddress=bc:5f:f4:*' --set 'description=New Batch Laptops'"
		),
		where="Filter target hosts (e.g., --where 'id=pc-*').",
		set="Field and new value to apply (e.g., --set 'description=Updated').",
	),
)

CONFIG_STATE_HELP = CommandHelp(
	# APPLY=HelpTexts()
	DELETE=HelpTexts(
		short="Delete configuration states.",
		long=(
			"Remove explicit client or depot configuration states. Target hosts revert to inherited server defaults.\n\n"
			"[bold]Examples:[/]\n"
			"opsi-cli datastore config-state delete --where 'objectId=host1.local' --where 'configId=clientconfig.windows.domain'"
		),
		where="Specify targets to wipe (e.g., --where 'objectId=host1.local').",
	),
	# EDIT=HelpTexts(),
	GENERAL=HelpTexts(
		short="View/change client config states.",
		long="Manage configuration states assigned to OPSI clients and depots.",
	),
	LIST=HelpTexts(
		short="List configuration state values.",
		long=(
			"Display configuration entries. Resolves the inheritance loop between global, depot, and client settings.\n\n"
			"[bold]Examples:[/]\n"
			"opsi-cli datastore config-state list --where 'configId=opsi.pc_proto*'"
		),
		where="Filter by ID or client (e.g., --where 'configId=opsi.pc_proto*').",
		all="Show every configuration state in the environment.",
	),
	UPDATE=HelpTexts(
		short="Override configuration state values.",
		long=(
			"Force an explicit value override for configuration states. Values must match defined data types.\n\n"
			"[bold]Examples:[/]\n"
			"opsi-cli datastore config-state update --where 'objectId=host1.local.*' --set 'values=pxelinux.cfg'"
		),
		where="Specify targets (e.g., --where 'objectId=host1.local.*').",
		set="Value to assign (e.g., --set 'values=pxelinux.cfg').",
	),
)

PRODUCT_HELP = CommandHelp(
	# APPLY=HelpTexts(),
	# DELETE=HelpTexts(),
	# EDIT=HelpTexts(),
	GENERAL=HelpTexts(
		short="Manage OPSI software products.",
		long="Unlock locked software products or clean up tracking data for uninstalled OPSI packages.",
	),
	# LIST=HelpTexts(),
	PURGE=HelpTexts(
		short="Purge backend traces of uninstalled products.",
		long=(
			"Run database garbage collection to permanently delete records for products no longer installed.\n\n"
			"[bold]Examples:[/]\n"
			"opsi-cli datastore product purge --where 'productId=old-java'"
		),
		where="Filter product IDs to purge (e.g., --where 'productId=old-java').",
		all="Wipe historical data for all uninstalled products.",
	),
	# UPDATE=HelpTexts(), #
	UNLOCK=HelpTexts(
		short="Unlock software products.",
		long=(
			"Unlock software products locked on specific depot servers.\n\n"
			"[bold]Examples:[/]\n"
			"opsi-cli datastore product unlock --where 'productId=firefox'"
			"opsi-cli datastore product unlock --where 'productId=win*'"
		),
		where="Target product and depot (e.g., --where 'productId=firefox').",
		all="Unlock all products across all depots globally.",
	),
)

PRODUCT_CLIENT_STATE_HELP = CommandHelp(
	APPLY=HelpTexts(
		short="Batch update action requests.",
		long=(
			"Set software action requests (e.g., setup/uninstall) in bulk via file input or stdin.\n\n"
			"[bold]Examples:[/]\n"
			"opsi-cli datastore product-client-state apply --input-file states.json"
		),
	),
	# DELETE=HelpTexts(), #
	# EDIT=HelpTexts(),   #
	GENERAL=HelpTexts(
		short="Manage product installation states.",
		long="View or trigger software installation statuses and action requests on client hosts.",
	),
	LIST=HelpTexts(
		short="List installation and pending actions.",
		long=(
			"Query the deployment grid for 'installed', 'pending', or 'failed' installation statuses.\n\n"
			"[bold]Examples:[/]\n"
			"opsi-cli datastore product-client-state list --where 'actionRequest=setup'"
		),
		where="Filter by field (e.g., --where 'actionRequest=setup').",
		all="Show records for every product on every client.",
	),
	# UPDATE=HelpTexts(), #
)

PRODUCT_PROPERTY_STATE_HELP = CommandHelp(
	# APPLY=HelpTexts(),
	# DELETE=HelpTexts(),
	# EDIT=HelpTexts(),
	GENERAL=HelpTexts(
		short="Manage product properties.",
		long="View custom software package configurations, such as installation flags or serial keys.",
	),
	LIST=HelpTexts(
		short="List product property assignments.",
		long=(
			"Display custom properties. Resolves inheritance between package defaults, depot adjustments, and client overrides.\n\n"
			"[bold]Examples:[/]\n"
			"opsi-cli datastore product-property-state list --where 'productId=firefox'"
		),
		where="Filter by package or property (e.g., --where 'productId=firefox').",
		all="Show all assignments, skipping filters.",
	),
	# UPDATE=HelpTexts(),
)

DATASTORE_HELP = CommandHelp(
	GENERAL=HelpTexts(
		short="Manage datastore objects.",
		long="General utility to manage datastore objects and related configuration data.",
	)
)
