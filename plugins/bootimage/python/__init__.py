# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
template for opsi-cli plugins
"""

import rich_click as click
from opsicommon.logging import get_logger
from opsicommon.objects import BoolConfig, Config, ConfigState, UnicodeConfig
from purecrypt import Crypt, Method

from opsicli.cli_helpers import OPSICLIGroup
from opsicli.decorators import dry_run_handling
from opsicli.io import Attribute, Metadata, OutputType, console_print, write_output
from opsicli.opsiservice import get_service_connection
from opsicli.plugin import OPSICLIPlugin

__version__ = "0.3.0"
__description__ = "Plugin to edit bootimage configs"


logger = get_logger("opsicli")


def set_linux_bootimage_cmdline_param(name: str, values: list[str], host_id: str | None = None) -> None:
	values = values or []
	config_id = f"netboot.linux-bootimage.cmdline.{name}"
	service = get_service_connection()

	configs: list[Config] = service.jsonrpc("config_getObjects", [[], {"id": config_id}])
	if not configs:
		description: str = f"Linux bootimage cmdline parameter {name} created by opsi-cli"
		if values and values[0].lower() in ("true", "false"):
			configs = [
				BoolConfig(
					id=config_id,
					description=description,
				)
			]
		else:
			configs = [
				UnicodeConfig(
					id=config_id,
					description=description,
					editable=True,
				)
			]
		if host_id:
			service.jsonrpc("config_createObjects", [configs])

	new_values: list[str | bool] = []
	if values:
		if isinstance(configs[0], BoolConfig):
			new_values = [values[0].lower() == "true"]
		else:
			new_values = [v for v in values]

	if not host_id:
		possible_values = configs[0].possibleValues or []
		for v in new_values:
			if v not in possible_values:
				possible_values.append(v)
		configs[0].setPossibleValues(possible_values)
		configs[0].setDefaultValues(new_values)
		service.jsonrpc("config_updateObjects", [configs])
		return

	service.jsonrpc(
		"configState_updateObjects",
		[
			ConfigState(
				configId=config_id,
				objectId=host_id,
				values=new_values,
			)
		],
	)


@click.group(cls=OPSICLIGroup, name="bootimage", short_help="Plugin for bootimage configuration")
@click.version_option(__version__, message="opsi-cli plugin bootimage, version %(version)s")
@click.option("--host", "--client", help="set value specific for this client", type=str)
@click.pass_context
@dry_run_handling()
def cli(ctx: click.Context, host: str | None) -> None:
	"""
	Custom plugin to edit bootimage append configs
	"""
	logger.trace("bootimage command")
	ctx.obj = {"host": host}


@cli.command(short_help="Set any bootimage (append) parameter")
@click.argument("parameter", nargs=1, type=str)
@click.argument("value", type=str, required=False)
@click.pass_context
def set_boot_parameter(ctx: click.Context, parameter: str, value: str | None = None) -> None:
	"""
	This subcommand sets an append parameter for opsi-linux-bootimage
	"""
	logger.trace("bootimage set-boot-parameter subcommand")
	if ctx.obj["host"]:
		logger.notice("Setting parameter %r for client %r", parameter, ctx.obj["host"])
	else:
		logger.notice("Setting parameter %r globally", parameter)

	if not value:
		# If no value is given, we assume it's a flag and set it to true
		value = "true"

	set_linux_bootimage_cmdline_param(name=parameter, values=[value], host_id=ctx.obj["host"])

	if ctx.obj["host"]:
		console_print(f"Parameter {parameter} set for client {ctx.obj['host']}.", output_type=OutputType.MESSAGE)
	else:
		console_print(f"Parameter {parameter} set globally.", output_type=OutputType.MESSAGE)


@cli.command(short_help="Set password hash bootimage parameter")
@click.argument("password", nargs=1, type=str)
@click.pass_context
def set_boot_password(ctx: click.Context, password: str) -> None:
	"""
	This subcommand hashes a given password and sets it as pwh for the opsi-linux-bootimage
	"""
	logger.trace("bootimage set-boot-password subcommand")
	password_hash = ""
	while not password_hash or "." in password_hash:
		salt = Crypt.generate_salt(Method.SHA512)
		salt = salt[:19]  # 16 bytes salt + 3 bytes $6$
		password_hash = Crypt.encrypt(password, salt)
	logger.notice("Setting linux bootimage cmdline parameter 'pwh'")

	set_linux_bootimage_cmdline_param(name="pwh", values=[password_hash], host_id=ctx.obj["host"])

	console_print("Password hash generated and applied successfully.", output_type=OutputType.MESSAGE)
	metadata = Metadata(
		attributes=[
			Attribute(id="password_hash", description="The password hash.", data_type="str"),
		]
	)
	write_output(
		data={"password_hash": password_hash},
		metadata=metadata,
		default_output_format=OutputFormat.PRETTY_JSON,
	)


class BootimagePlugin(OPSICLIPlugin):
	name: str = "bootimage"
	description: str = __description__
	version: str = __version__
	cli = cli
	flags: list[str] = []
