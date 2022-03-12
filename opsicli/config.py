# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

general configuration
"""

import platform
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import rich_click as click  # type: ignore[import]
from opsicommon.logging import (  # type: ignore[import]
	DEFAULT_COLORED_FORMAT,
	DEFAULT_FORMAT,
	logging_config,
)
from opsicommon.utils import Singleton  # type: ignore[import]
from pydantic import BaseModel, validator  # pylint: disable=no-name-in-module
from ruamel.yaml import YAML

from opsicli.types import (
	Bool,
	Directory,
	File,
	LogLevel,
	OPSIServiceUrl,
	OutputFormat,
	Password,
)

DEFAULT_CONFIG_FILES = ["~/.config/opsi-cli/opsi-cli.yaml", "/etc/opsi/opsi-cli.yaml"]


@lru_cache(maxsize=1)
def get_python_path() -> str:
	for pyversion in ("python3", "python"):
		result = shutil.which(pyversion)
		if result:
			return result
	raise RuntimeError("Could not find python path")


class ConfigItem(BaseModel):  # pylint: disable=too-few-public-methods
	class Config:  # pylint: disable=too-few-public-methods
		validate_assignment = True

	name: str
	type: Any
	multiple: bool = False
	default: Optional[Union[List[Any], Any]] = None
	description: Optional[str] = None
	plugin: Optional[str] = None
	group: Optional[str] = None
	value: Union[List[Any], Any] = None

	@validator("default")
	def validate_default(cls, default, values, **kwargs):  # pylint: disable=no-self-argument,no-self-use,unused-argument
		if default is not None:
			if values["multiple"]:
				default = [values["type"](d) for d in default]
			else:
				default = values["type"](default)
		return default

	@validator("value", always=True)
	def validate_value(cls, value, values, **kwargs):  # pylint: disable=no-self-argument,no-self-use,unused-argument
		if value is None:
			value = values["default"]
		if value is not None:
			if values["multiple"]:
				value = [values["type"](v) for v in value]
			else:
				value = values["type"](value)
		return value


CONFIG_ITEMS = [
	ConfigItem(name="log_file", type=File, group="General", description="Log to this file"),
	ConfigItem(
		name="log_level_file",
		type=LogLevel,
		group="General",
		default="none",
		description=f"The log level for the log file. Possible values are:\n\n{LogLevel.possible_values_for_description}",
	),
	ConfigItem(
		name="log_level_stderr",
		type=LogLevel,
		group="General",
		default="warning",
		description=f"The log level for the console (stderr). Possible values are:\n\n{LogLevel.possible_values_for_description}",
	),
	ConfigItem(name="color", type=Bool, group="General", default=True, description="Enable or disable colorized output"),
	ConfigItem(
		name="output_format",
		type=OutputFormat,
		group="General",
		default="auto",
		description=f"Set output format. Possible values are: {OutputFormat.possible_values_for_description}",
	),
	ConfigItem(
		name="output_file",
		type=File,
		group="General",
		default="-",
		description="Write data to this file",
	),
	ConfigItem(name="metadata", type=Bool, group="General", default=False, description="Enable or disable output of metadata"),
	ConfigItem(name="header", type=Bool, group="General", default=True, description="Enable or disable header output"),
	ConfigItem(
		name="service_url",
		type=OPSIServiceUrl,
		group="Opsi service",
		default="https://localhost:4447",
		description="URL of the opsi service to connect",
	),
	ConfigItem(name="username", type=str, group="Opsi service", description="Username for opsi service connection"),
	ConfigItem(name="password", type=Password, group="Opsi service", description="Password for opsi service connection"),
]

if platform.system().lower() == "windows":
	# TODO: use a temporary directory to store plugins (Permission issue)
	_user_lib_dir = Path(tempfile.gettempdir()) / "opsicli"
else:
	_user_lib_dir = Path.home() / ".local" / "lib" / "opsicli"

CONFIG_ITEMS.extend(
	[
		ConfigItem(name="plugin_dirs", type=Directory, multiple=True, group="General", default=["plugins", _user_lib_dir / "plugins"]),
		ConfigItem(name="lib_dir", type=Directory, group="General", default=_user_lib_dir / "lib"),
	]
)

DEFAULT_CONFIG_FILE = None
for config_file in DEFAULT_CONFIG_FILES:
	config_path = Path(config_file).expanduser().absolute()
	if config_path.exists():
		DEFAULT_CONFIG_FILE = config_path
		break
CONFIG_ITEMS.append(
	ConfigItem(name="config_file", type=File, group="General", default=DEFAULT_CONFIG_FILE, description="Config file location")
)


class Config(metaclass=Singleton):  # pylint: disable=too-few-public-methods
	def __init__(self) -> None:
		self._config: Dict[str, ConfigItem] = {}
		for item in CONFIG_ITEMS:
			self.add_config_item(item)

	def add_config_item(self, config_item: ConfigItem):
		self._config[config_item.name] = config_item

	def get_config_item(self, name: str) -> ConfigItem:
		return self._config[name]

	def get_config_items(self) -> List[ConfigItem]:
		return list(self._config.values())

	def get_values(self) -> Dict[str, Any]:
		values = {}
		for name, item in self._config.items():
			values[name] = item.value
		return values

	def set_values(self, values: Dict[str, Any]) -> None:
		for name, value in values.items():
			self._config[name].value = value

	def read_config_file(self):
		if not self.config_file:
			return
		yaml = YAML()
		with open(self.config_file, "r", encoding="utf-8") as file:
			data = yaml.load(file.read())
			for key, val in data.items():
				if key in self._config:
					self._config[key].value = val

	def set_logging_config(self):
		logging_config(
			log_file=self.log_file,
			file_level=self.log_level_file,
			stderr_level=self.log_level_stderr,
			stderr_format=DEFAULT_COLORED_FORMAT if self.color else DEFAULT_FORMAT,
		)

	def process_option(self, ctx: click.Context, param: click.Option, value: Any):  # pylint: disable=unused-argument
		if param.name not in self._config:
			return
		try:
			self._config[param.name].value = value
		except ValueError as err:
			msg = str(err)
			if hasattr(err, "errors"):
				msg = err.errors()[0]["msg"]  # type: ignore[attr-defined]
			raise click.BadParameter(msg, ctx=ctx, param=param) from err

		if param.name == "config_file":
			self.read_config_file()
		elif param.name in ("log_file", "file_level", "log_level_stderr", "color"):
			self.set_logging_config()

		ctx.default_map = {}
		for key, item in self._config.items():
			ctx.default_map[key] = item.value

	def get_default(self, name: str) -> Any:
		return self._config[name].default

	def get_description(self, name: str) -> Optional[str]:
		return self._config[name].description

	def get_items_by_group(self) -> Dict[str, List[ConfigItem]]:
		items: Dict[str, List[ConfigItem]] = {}
		for item in self._config.values():
			group = item.group or ""
			if group not in items:
				items[group] = []
			items[group].append(item)
		return items

	def __getattr__(self, name: str) -> Any:
		if not name.startswith("_") and name in self._config:
			return self._config[name].value
		raise AttributeError(name)

	def __setattr__(self, name: str, value: Any) -> None:
		if not name.startswith("_") and name in self._config:
			self._config[name].value = value
			return
		super().__setattr__(name, value)


config = Config()
