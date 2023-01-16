# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

general configuration
"""

import os
import platform
import sys
from copy import deepcopy
from dataclasses import InitVar, asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import rich_click as click  # type: ignore[import]
from click.core import ParameterSource  # type: ignore[import]
from opsicommon.logging import (  # type: ignore[import]
	DEFAULT_COLORED_FORMAT,
	DEFAULT_FORMAT,
	LOG_ESSENTIAL,
	LOG_NONE,
	get_logger,
	logging_config,
	secret_filter,
)
from opsicommon.utils import Singleton  # type: ignore[import]
from ruamel.yaml import YAML  # type: ignore[import]

from opsicli.types import (
	Attributes,
	Bool,
	Directory,
	File,
	LogLevel,
	OPSIService,
	OPSIServiceUrlOrServiceName,
	OutputFormat,
	Password,
)

IN_COMPLETION_MODE = "_OPSI_CLI_COMPLETE" in os.environ

logger = get_logger("opsicli")


class ConfigValueSource(Enum):
	DEFAULT = "default"
	COMMANDLINE = "commandline"
	ENVIRONMENT = "environment"
	CONFIG_FILE_SYSTEM = "config_file_system"
	CONFIG_FILE_USER = "config_file_user"


logging_config(stderr_level=LOG_ESSENTIAL, file_level=LOG_NONE)
# logging_config(stderr_level=9)


@dataclass
class ConfigValue:  # pylint: disable=too-many-instance-attributes
	type: Any
	value: Any
	source: ConfigValueSource | None = None

	def __setattr__(self, name: str, value: Any) -> None:
		if name == "value" and value is not None:
			if not isinstance(value, self.type):
				if isinstance(value, dict):
					value = self.type(**value)
				else:
					value = self.type(value)
		self.__dict__[name] = value

	def __repr__(self) -> str:
		return f"<ConfigValue value={self.value!r}, source={self.source}>"

	def __str__(self) -> str:
		if self.source:
			return f"{self.value} ({ConfigValueSource(self.source).value})"
		return f"{self.value}"


@dataclass
class ConfigItem:  # pylint: disable=too-many-instance-attributes
	name: str
	type: Any
	multiple: bool = False
	key: str | None = None
	description: str | None = None
	plugin: str | None = None
	group: str | None = None
	default: InitVar[Any] = None
	value: InitVar[Any] = None
	_default: list[ConfigValue] | ConfigValue | None = None
	_value: list[ConfigValue] | ConfigValue | None = None

	def __post_init__(self, default: Any, value: Any) -> None:
		self.set_default(default)
		self.set_value(value)

	def __setattr__(self, name: str, value: Any) -> None:
		self._set_value(name, value)

	def __getattribute__(self, name: str) -> Any:
		if name in ("default", "value"):
			attribute = f"_{name}"
			if self.multiple:
				return [config_value.value for config_value in getattr(self, attribute) or []]
			if getattr(self, attribute) is None:
				return None
			return getattr(self, attribute).value
		return super().__getattribute__(name)

	def _set_value(self, name: str, value: Any, source: ConfigValueSource | None = None) -> None:
		if name in ("default", "value"):
			if name == "default":
				source = ConfigValueSource.DEFAULT
			attribute = f"_{name}"

			if value is None:
				if attribute == "_value":
					self.__dict__[attribute] = deepcopy(self.__dict__["_default"])
				elif self.multiple:
					self.__dict__[attribute] = []
				else:
					self.__dict__[attribute] = None
			else:
				if self.multiple:
					for val in value:
						self._add_value(name, val, source)
				else:
					self.__dict__[attribute] = ConfigValue(self.type, value, source)
		else:
			self.__dict__[name] = value

	def set_value(self, value: Any, source: ConfigValueSource | None = None) -> None:
		self._set_value("value", value, source)  # pylint: disable=unnecessary-dunder-call

	def set_default(self, value: Any) -> None:
		self._set_value("default", value, ConfigValueSource.DEFAULT)  # pylint: disable=unnecessary-dunder-call

	def _add_value(self, attribute: str, value: Any, source: ConfigValueSource | None = None) -> None:
		if attribute not in ("default", "value"):
			raise ValueError(f"Invalid attribute '{attribute}'")
		if not self.multiple:
			raise ValueError("Only one value allowed")
		attribute = f"_{attribute}"
		if not self.__dict__.get(attribute):
			self.__dict__[attribute] = []
		config_value = ConfigValue(self.type, value, source)
		if self.key:
			key_val = getattr(config_value.value, self.key)
			for idx, config_val in enumerate(self.__dict__[attribute]):
				if getattr(config_val.value, self.key) == key_val:
					# Replace
					self.__dict__[attribute][idx] = config_value
					return
		self.__dict__[attribute].append(config_value)

	def add_value(self, value: Any, source: ConfigValueSource | None = None) -> None:
		self._add_value("value", value, source)

	def _remove_value(self, attribute: str, value: Any) -> None:
		if attribute not in ("default", "value"):
			raise ValueError(f"Invalid attribute '{attribute}'")
		if not self.multiple:
			raise ValueError("Only one value allowed")
		attribute = f"_{attribute}"
		self.__dict__[attribute].remove(value)

	def remove_value(self, value: Any) -> None:
		return self._remove_value("value", value)

	def get_value(self, value_only: bool = True) -> Any:
		if value_only:
			return self.value
		return self._value

	def get_values(self, value_only: bool = True, sources: list[ConfigValueSource] | None = None) -> list[Any]:
		values = [
			val.value if value_only else val
			for val in (self._value if self.multiple else [self._value])  # type: ignore[union-attr,list-item] # _value can be List or Scalar
			if val and (not sources or val.source in sources)
		]
		return values

	def get_default(self, value_only: bool = True) -> Any:
		if value_only:
			return self.default
		return self._default

	def as_dict(self) -> dict[str, Any]:
		dict_ = asdict(self)
		dict_["value"] = dict_.pop("_value")
		dict_["default"] = dict_.pop("_default")
		return dict_

	def __repr__(self) -> str:
		return f"<ConfigItem name={self.name!r}, default={self.default}, value={repr(self.value)}>"


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
		name="service",
		type=OPSIServiceUrlOrServiceName,
		group="Opsi service",
		default="https://localhost:4447",
		description="URL or name of a configured service to connect.",
	),
	ConfigItem(name="username", type=str, group="Opsi service", description="Username for opsi service connection."),
	ConfigItem(name="password", type=Password, group="Opsi service", description="Password for opsi service connection."),
	ConfigItem(name="services", type=OPSIService, description="Configured opsi services.", multiple=True, key="name"),
	ConfigItem(
		name="dry_run",
		type=Bool,
		group="General",
		default=False,
		description="Simulation only. Does not perform actions.",
	),
]

if platform.system().lower() == "windows":
	_user_lib_dir = Path(os.getenv("APPDATA") or ".") / "opsi-cli" / "Local" / "Lib"
else:
	_user_lib_dir = Path.home() / ".local" / "lib" / "opsi-cli"

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

_config_file_system = None  # pylint: disable=invalid-name
_config_file_user = None  # pylint: disable=invalid-name
if platform.system().lower() == "windows":
	# APPDATA points to ...\AppData\Roaming
	_config_file_user = Path(os.getenv("APPDATA") or ".") / "opsi-cli" / "opsi-cli.yaml"
else:
	_config_file_system = Path("/etc/opsi/opsi-cli.yaml")
	_config_file_user = Path("~/.config/opsi-cli/opsi-cli.yaml")

CONFIG_ITEMS.extend(
	[
		ConfigItem(
			name="config_file_system",
			type=File,
			group="General",
			default=_config_file_system,
			description="System wide config file location",
		),
		ConfigItem(
			name="config_file_user",
			type=File,
			group="General",
			default=_config_file_user,
			description="User specific config file",
		),
	]
)


class Config(metaclass=Singleton):  # pylint: disable=too-few-public-methods
	def __init__(self) -> None:
		self._options_processed: set[str] = set()
		self._config: dict[str, ConfigItem] = {}
		for item in CONFIG_ITEMS:
			self.add_config_item(item)

	def add_config_item(self, config_item: ConfigItem) -> None:
		self._config[config_item.name] = config_item

	def get_config_item(self, name: str) -> ConfigItem:
		return self._config[name]

	def get_config_items(
		self,
	) -> list[ConfigItem]:
		return list(self._config.values())

	def get_values(self) -> dict[str, Any]:
		values = {}
		for name, item in self._config.items():
			values[name] = item.value
		return values

	def set_values(self, values: dict[str, Any]) -> None:
		for name, value in values.items():
			self._config[name].value = value

	def read_config_files(self) -> None:
		for file_type in ("config_file_system", "config_file_user"):
			config_file = getattr(self, file_type, None)
			if not config_file or not config_file.exists():
				continue
			source = ConfigValueSource.CONFIG_FILE_SYSTEM if file_type == "config_file_system" else ConfigValueSource.CONFIG_FILE_USER
			with open(config_file, "r", encoding="utf-8") as file:
				data = YAML().load(file.read())
				for key, value in data.items():
					config_item = self._config.get(key)
					if not config_item:
						continue

					if not config_item.multiple and config_item.get_values(value_only=False, sources=[ConfigValueSource.COMMANDLINE]):
						# Do not override cmdline arguments
						continue

					if config_item.key:
						new_value = []
						for akey, adict in value.items():
							adict[config_item.key] = akey
							new_value.append(adict)
						value = new_value

					if config_item.multiple:
						for val in value:
							if hasattr(config_item.type, "from_yaml"):
								val = config_item.type.from_yaml(val)
							config_item.add_value(val, source)
					else:
						if hasattr(config_item.type, "from_yaml"):
							value = config_item.type.from_yaml(value)
						config_item.set_value(value, source)

	def write_config_files(self, sources: list[ConfigValueSource] | None = None) -> None:
		logger.info("Writing config files")
		for file_type in ("config_file_system", "config_file_user"):
			config_file = getattr(self, file_type, None)
			source = ConfigValueSource.CONFIG_FILE_SYSTEM if file_type == "config_file_system" else ConfigValueSource.CONFIG_FILE_USER
			if sources and source not in sources:
				continue
			if not config_file:
				continue

			data = {}
			if config_file.exists():
				with open(config_file, "r", encoding="utf-8") as file:
					data = YAML().load(file)

			for config_item in self._config.values():
				values = [val for val in config_item.get_values(value_only=False) if val and val.source == source]
				if not values:
					continue
				yaml_values = [val.value.to_yaml() if hasattr(val.value, "to_yaml") else val.value for val in values if val]

				if config_item.multiple:
					if config_item.key:
						data[config_item.name] = {}
						for yaml_val in yaml_values:
							key = yaml_val.pop(config_item.key)
							data[config_item.name][key] = yaml_val
					else:
						data[config_item.name] = yaml_values
				else:
					data[config_item.name] = yaml_values[0]
			if not config_file.parent.exists():
				logger.debug("Creating directory %s", config_file.parent)
				config_file.parent.mkdir(parents=True)
			with open(config_file, "w", encoding="utf-8") as file:  # IDEA: save file and restore on error
				logger.debug("Writing file %s", config_file)
				YAML().dump(data, file)

	def set_logging_config(self) -> None:
		logging_config(
			log_file=self.log_file,
			file_level=self.log_level_file,
			stderr_level=self.log_level_stderr,
			stderr_format=DEFAULT_COLORED_FORMAT if self.color else DEFAULT_FORMAT,
		)

	def get_click_option(self, name: str, **kwargs: str | bool) -> Callable:
		config_item = self._config[name]
		long_option = kwargs.pop("long_option", None)
		if long_option is None:
			long_option = f"--{name.replace('_', '-')}"
			if isinstance(config_item.type, Bool):
				long_option = f"{long_option}/--no-{long_option.lstrip('--')}"
		_kwargs = {
			"type": getattr(config_item.type, "click_type", config_item.type),
			"callback": self.process_option,
			"metavar": name.upper(),
			"envvar": f"OPSICLI_{name.upper()}",
			"help": config_item.description,
			"default": config_item.get_default(),
			"show_default": True
		}
		_args = [str(long_option)] + ([str(kwargs.pop("short_option"))] if "short_option" in kwargs else [])
		_kwargs.update(kwargs)
		return click.option(*_args, **_kwargs)

	def process_option(self, ctx: click.Context, param: click.Option, value: Any) -> None:  # pylint: disable=unused-argument
		if param.name is None:
			return
		param_source = ctx.get_parameter_source(param.name)
		if IN_COMPLETION_MODE:
			return
		if param.name not in self._config:
			return

		try:
			source = None
			if param_source == ParameterSource.COMMANDLINE:
				source = ConfigValueSource.COMMANDLINE
			elif param_source == ParameterSource.ENVIRONMENT:
				source = ConfigValueSource.ENVIRONMENT
			if source:
				self._config[param.name].set_value(value, source)
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

		if param.name in ("log_file", "log_level_file", "log_level_stderr", "color"):
			self.set_logging_config()

	def get_default(self, name: str) -> Any:
		return self._config[name].get_default()

	def get_description(self, name: str) -> str | None:
		return self._config[name].description

	def get_items_by_group(self) -> dict[str, list[ConfigItem]]:
		items: dict[str, list[ConfigItem]] = {}
		for item in self._config.values():
			group = item.group or ""
			if group not in items:
				items[group] = []
			items[group].append(item)
		return items

	def __getattr__(self, name: str) -> Any:
		if not name.startswith("_") and name in self._config:
			return self._config[name].get_value()
		raise AttributeError(name)

	def __setattr__(self, name: str, value: Any) -> None:
		if not name.startswith("_") and name in self._config:
			if name == "password" and value:
				secret_filter.add_secrets(value)
			self._config[name].set_value(value)
			return
		super().__setattr__(name, value)


config = Config()
