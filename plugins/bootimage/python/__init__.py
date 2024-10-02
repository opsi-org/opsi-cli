"""
template for opsi-cli plugins
"""

import rich_click as click  # type: ignore[import]
from opsicommon.logging import get_logger
from opsicommon.objects import Config, ConfigState
from purecrypt import Crypt, Method  # type: ignore[import]

from opsicli.opsiservice import get_service_connection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.2.0"
__description__ = "Plugin to edit bootimage configs"


logger = get_logger("opsicli")


def patch_values(patch_dict: dict[str, str], values: list[str]) -> list[str]:
	for key, value in patch_dict.items():
		for index, entry in enumerate(values):
			if entry.startswith(f"{key}="):
				new_entry = f"{key}={value}"
				logger.debug("Replacing %s with %s", entry, new_entry)
				values[index] = new_entry
				break
		else:
			new_entry = f"{key}={value}"
			logger.debug("Adding new entry %s", new_entry)
			values.append(new_entry)
	return values


def patch_flags(flags: list[str], values: list[str]) -> list[str]:
	for entry in flags:
		if entry not in values:
			logger.debug("Adding new entry %s", entry)
			values.append(entry)
	return values


def remove_old_password_hashes(values: dict[str, str] | None = None, flags: list[str] | None = None) -> None:
	values = values or {}
	flags = flags or []
	service = get_service_connection()
	configs: list[Config] = service.jsonrpc("config_getObjects", [[], {"id": "opsi-linux-bootimage.append"}])
	if not configs[0].possibleValues:
		configs[0].possibleValues = []
	if not configs[0].defaultValues:
		configs[0].defaultValues = []
	for element in configs[0].possibleValues:
		print(f"looping through possible values: {element}")
		if element.startswith("pwh="):
			print(f"removing old password hash: {element}")
			configs[0].possibleValues.remove(element)
	for element in configs[0].defaultValues:
		print(f"looping through default values: {element}")
		if element.startswith("pwh="):
			print(f"removing old password hash: {element}")
			configs[0].defaultValues.remove(element)
	service.jsonrpc("config_updateObjects", [configs])


def set_append_values(values: dict[str, str] | None = None, flags: list[str] | None = None, client: str | None = None) -> None:
	values = values or {}
	flags = flags or []
	service = get_service_connection()
	if client:
		config_states: list[ConfigState] = service.jsonrpc(
			"configState_getObjects", [[], {"configId": "opsi-linux-bootimage.append", "objectId": client}]
		)
		new_values = [f"{key}={value}" for key, value in values.items()] + flags
		if not config_states:
			service.jsonrpc("configState_create", ["opsi-linux-bootimage.append", client, new_values])
		else:
			config_states[0].values = patch_values(values, config_states[0].values or [])
			config_states[0].values = patch_flags(flags, config_states[0].values or [])
			service.jsonrpc("configState_updateObjects", [config_states])
		return

	configs: list[Config] = service.jsonrpc("config_getObjects", [[], {"id": "opsi-linux-bootimage.append"}])
	if not configs[0].possibleValues:
		configs[0].possibleValues = []
	if not configs[0].defaultValues:
		configs[0].defaultValues = []
	new_values = patch_values(values, configs[0].defaultValues)
	new_values = patch_flags(flags, new_values)
	for new_value in new_values:
		if new_value not in configs[0].possibleValues:
			configs[0].possibleValues.append(new_value)
	configs[0].defaultValues = new_values
	service.jsonrpc("config_updateObjects", [configs])


@click.group(name="bootimage", short_help="Plugin for bootimage configuration")
@click.version_option(__version__, message="opsi-cli plugin bootimage, version %(version)s")
@click.option("--client", help="set value specific for this client", type=str)
@click.pass_context
def cli(ctx: click.Context, client: str | None) -> None:
	"""
	Custom plugin to edit bootimage append configs
	"""
	logger.trace("bootimage command")
	ctx.obj = {"client": client}


@cli.command(short_help="Set any bootimage (append) parameter")
@click.argument("parameter", nargs=1, type=str)
@click.argument("value", type=str, required=False)
@click.pass_context
def set_boot_parameter(ctx: click.Context, parameter: str, value: str | None = None) -> None:
	"""
	This subcommand sets an append parameter for opsi-linux-bootimage
	"""
	logger.trace("bootimage set-boot-parameter subcommand")
	if ctx.obj["client"]:
		logger.notice("Setting parameter %r for client %r", parameter, ctx.obj["client"])
	else:
		logger.notice("Setting parameter %r globally", parameter)
	if value:
		set_append_values(values={parameter: value}, client=ctx.obj["client"])
	else:
		set_append_values(flags=[parameter], client=ctx.obj["client"])


@cli.command(short_help="Set password hash bootimage parameter")
@click.argument("password", nargs=1, type=str)
@click.pass_context
def set_boot_password(ctx: click.Context, password: str) -> None:
	"""
	This subcommand hashes a given password and sets it as pwh for the opsi-linux-bootimage
	"""
	logger.trace("bootimage set-boot-password subcommand")
	hashed_password = ""
	while not hashed_password or "." in hashed_password:
		salt = Crypt.generate_salt(Method.SHA512)
		salt = salt[:19]  # 16 bytes salt + 3 bytes $6$
		hashed_password = Crypt.encrypt(password, salt)
	logger.notice("Setting pwh append parameter")
	print("Hashed password is:", hashed_password)
	remove_old_password_hashes()
	set_append_values(values={"pwh": hashed_password}, client=ctx.obj["client"])


class BootimagePlugin(OPSICLIPlugin):
	name: str = "bootimage"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = []
