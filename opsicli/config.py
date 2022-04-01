# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

general configuration
"""

import os
import platform
import shutil
import sys
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import rich_click as click  # type: ignore[import]
from opsicommon.logging import (  # type: ignore[import]
	DEFAULT_COLORED_FORMAT,
	DEFAULT_FORMAT,
	LOG_ESSENTIAL,
	LOG_NONE,
	logging_config,
	secret_filter,
)
from opsicommon.utils import Singleton  # type: ignore[import]
from ruamel.yaml import YAML

from opsicli.types import (
	Attributes,
	Bool,
	Directory,
	File,
	LogLevel,
	OPSIService,
	OPSIServiceUrl,
	OutputFormat,
	Password,
)

IN_COMPLETION_MODE = "_OPSI_CLI_COMPLETE" in os.environ

logging_config(stderr_level=LOG_ESSENTIAL, file_level=LOG_NONE)


@lru_cache(maxsize=1)
def get_python_path() -> str:
	for pyversion in ("python3", "python"):
		result = shutil.which(pyversion)
		if result:
			return result
	raise RuntimeError("Could not find python path")


@dataclass
class ConfigItem:  # pylint: disable=too-many-instance-attributes
	name: str
	type: Any
	multiple: bool = False
	key: Optional[str] = None
	default: Optional[Union[List[Any], Any]] = None
	description: Optional[str] = None
	plugin: Optional[str] = None
	group: Optional[str] = None
	value: Union[List[Any], Any] = None

	def __setattr__(self, name, value):
		# if hasattr(self, "name") and self.name == "services":
		# 	print("===", self.name, value)
		if name == "default":
			if value is not None:
				if self.multiple:
					for val in value:
						self._add_value("default", val)
					return
				value = self.type(value)
			elif self.multiple:
				value = []
		elif name == "value":
			if value is None:
				value = deepcopy(self.default)
			else:
				if self.multiple:
					for val in value:
						self._add_value("value", val)
					return
				value = self.type(value)
		self.__dict__[name] = value

	def _add_value(self, attribute, value):
		if not self.multiple:
			raise ValueError("Only one value allowed")
		if not self.__dict__.get(attribute):
			self.__dict__[attribute] = []
		if not isinstance(value, self.type):
			if isinstance(value, dict):
				value = self.type(**value)
			else:
				value = self.type(value)
		if self.key:
			key_val = getattr(value, self.key)
			for val in self.__dict__[attribute]:
				if getattr(val, self.key) == key_val:
					# Replace
					val = value
					return
		self.__dict__[attribute].append(value)

	def add_value(self, value):
		return self._add_value("value", value)

	def as_dict(self):
		return asdict(self)


CONFIG_ITEMS = [
	ConfigItem(name="log_file", type=File, group="General", description="Log to the specified file."),
	ConfigItem(
		name="log_level_file",
		type=LogLevel,
		group="General",
		default="none",
		description=f"The log level for the log file. Possible values are:\n\n{LogLevel.possible_values_for_description}.",
	),
	ConfigItem(
		name="log_level_stderr",
		type=LogLevel,
		group="General",
		default="none",
		description=f"The log level for the console (stderr). Possible values are:\n\n{LogLevel.possible_values_for_description}.",
	),
	ConfigItem(name="color", type=Bool, group="General", default=True, description="Enable or disable colorized output."),
	ConfigItem(
		name="output_format",
		type=OutputFormat,
		group="IO",
		default="auto",
		description=f"Set output format. Possible values are: {OutputFormat.possible_values_for_description}.",
	),
	ConfigItem(
		name="output_file",
		type=File,
		group="IO",
		default="-",
		description="Write data to the given file.",
	),
	ConfigItem(
		name="input_file",
		type=File,
		group="IO",
		default="-",
		description="Read data from the given file.",
	),
	ConfigItem(name="interactive", type=Bool, group="IO", default=sys.stdin.isatty(), description="Enable or disable interactive mode."),
	ConfigItem(name="metadata", type=Bool, group="IO", default=False, description="Enable or disable output of metadata."),
	ConfigItem(name="header", type=Bool, group="IO", default=True, description="Enable or disable header for data input and output."),
	ConfigItem(
		name="attributes",
		type=Attributes,
		group="IO",
		default=None,
		description="Select data attributes ([metavar]all[/metavar] selects all available attributes).",
	),
	ConfigItem(
		name="service_url",
		type=OPSIServiceUrl,
		group="Opsi service",
		default="https://localhost:4447",
		description="URL of the opsi service to connect.",
	),
	ConfigItem(name="username", type=str, group="Opsi service", description="Username for opsi service connection."),
	ConfigItem(name="password", type=Password, group="Opsi service", description="Password for opsi service connection."),
	ConfigItem(name="services", type=OPSIService, description="Configured opsi services.", multiple=True, key="name"),
]

if platform.system().lower() == "windows":
	# TODO: use a temporary directory to store plugins (Permission issue)
	_user_lib_dir = Path(tempfile.gettempdir()) / "opsicli"
else:
	_user_lib_dir = Path.home() / ".local" / "lib" / "opsicli"

CONFIG_ITEMS.extend(
	[
		ConfigItem(name="user_lib_dir", type=Directory, group="General", default=_user_lib_dir),
		ConfigItem(name="python_lib_dir", type=Directory, group="General", default=_user_lib_dir / "lib"),
	]
)


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
	_plugin_bundle_dir = Path(sys._MEIPASS) / "plugins"  # type: ignore[attr-defined] # pylint: disable=protected-access
else:
	_plugin_bundle_dir = Path("plugins").resolve()

_plugin_system_dir = None  # pylint: disable=invalid-name
if platform.system().lower() == "linux":
	_plugin_system_dir = Path("/var/lib/opsi-cli/plugins")

CONFIG_ITEMS.extend(
	[
		ConfigItem(name="plugin_bundle_dir", type=Directory, group="General", default=_plugin_bundle_dir),
		ConfigItem(name="plugin_system_dir", type=Directory, group="General", default=_plugin_system_dir),
		ConfigItem(name="plugin_user_dir", type=Directory, group="General", default=_user_lib_dir / "plugins"),
	]
)

CONFIG_ITEMS.extend(
	[
		ConfigItem(
			name="config_file_system",
			type=File,
			group="General",
			default="~/.config/opsi-cli/opsi-cli.yaml",
			description="System wide config file location",
		),
		ConfigItem(
			name="config_file_user",
			type=File,
			group="General",
			default="/etc/opsi/opsi-cli.yaml",
			description="User specific config file",
		),
	]
)


class Config(metaclass=Singleton):  # pylint: disable=too-few-public-methods
	def __init__(self) -> None:
		self._options_processed: Set[str] = set()
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

	def read_config_files(self):
		for config_file in (self.config_file_system, self.config_file_user):
			if not config_file or not config_file.exists():
				continue
			with open(config_file, "r", encoding="utf-8") as file:
				data = YAML().load(file.read())
				for key, val in data.items():
					config_item = self._config.get(key)
					if not config_item:
						continue
					if config_item.key:
						for c_key, kwargs in val.items():
							kwargs[config_item.key] = c_key
							config_item.add_value(kwargs)
					else:
						config_item.value = val

	def set_logging_config(self):
		logging_config(
			log_file=self.log_file,
			file_level=self.log_level_file,
			stderr_level=self.log_level_stderr,
			stderr_format=DEFAULT_COLORED_FORMAT if self.color else DEFAULT_FORMAT,
		)

	def process_option(self, ctx: click.Context, param: click.Option, value: Any):  # pylint: disable=unused-argument
		if IN_COMPLETION_MODE:
			return
		if param.name not in self._config:
			return
		try:
			self._config[param.name].value = value
		except ValueError as err:
			msg = str(err)
			if hasattr(err, "errors"):
				msg = err.errors()[0]["msg"]  # type: ignore[attr-defined]
			raise click.BadParameter(msg, ctx=ctx, param=param) from err

		ctx.default_map = {}
		for key, item in self._config.items():
			ctx.default_map[key] = item.value

		self._options_processed.add(param.name)

		test_params = ("config_file_system", "config_file_user")
		if param.name in test_params:
			if all(param in self._options_processed for param in test_params):
				self.read_config_files()

		if param.name in ("log_file", "file_level", "log_level_stderr", "color"):
			self.set_logging_config()

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
			if name == "password" and value:
				secret_filter.add_secrets(value)
			self._config[name].value = value
			return
		super().__setattr__(name, value)


config = Config()
