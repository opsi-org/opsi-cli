# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli - command line interface for opsi

types
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from opsicli.config import COMPLETION_MODE, DEFAULT_SESSION_LIFETIME

if not COMPLETION_MODE:
	import rich_click as click
else:
	# Loads faster
	import click

from opsi.logging import LEVEL_TO_OPSI_LEVEL, NAME_TO_LEVEL

from opsicli.utils import decrypt, encrypt


class classproperty(property):
	def __get__(self, obj: object, objtype: type | None = None) -> Any:
		return super().__get__(objtype)


class LogLevel(int):
	possible_values = list(reversed([v.lower() for v in NAME_TO_LEVEL]))
	possible_values_for_description = ", ".join(
		[f"[metavar]{name}[/metavar]/[metavar]{LEVEL_TO_OPSI_LEVEL[NAME_TO_LEVEL[name.upper()]]}[/metavar]" for name in possible_values]
	)

	def __new__(cls, value: str | int) -> LogLevel:
		try:
			value = min(9, max(0, int(value)))
		except ValueError:
			try:
				value = LEVEL_TO_OPSI_LEVEL[NAME_TO_LEVEL[str(value).upper()]]
			except KeyError:
				raise ValueError(f"{value!r} is not a valid log level, choose one of: {cls.possible_values_for_description}") from None
		return super().__new__(cls, value)

	def to_yaml(self) -> int:
		return int(self)


class Limit(int):
	click_type = click.IntRange(min=0)

	def __new__(cls, value: str | int) -> Limit:
		value = int(value)
		if value < 0:
			raise ValueError("limit must be greater than or equal to 0")
		return super().__new__(cls, value)

	def to_yaml(self) -> int:
		return int(self)


class ConfigStrEnum(StrEnum):
	@classproperty
	def possible_values(cls) -> list[str]:
		return [v.value for v in OutputFormat]

	@classproperty
	def possible_values_for_description(self) -> str:
		return ", ".join([f"[metavar]{v.value}[/metavar]" for v in OutputFormat])

	def to_yaml(self) -> str:
		return self.value


class OutputFormat(ConfigStrEnum):
	TABLE = "table"
	CSV = "csv"
	JSON = "json"
	PRETTY_JSON = "pretty-json"
	MSGPACK = "msgpack"
	KEY_VALUE = "key-value"
	AUTO = "auto"


class EditFormat(ConfigStrEnum):
	CSV = "csv"
	JSON = "json"
	PRETTY_JSON = "pretty-json"
	KEY_VALUE = "key-value"
	AUTO = "auto"

	@property
	def file_extension(self) -> str:
		return {
			self.CSV: "csv",
			self.JSON: "json",
			self.PRETTY_JSON: "json",
			self.KEY_VALUE: "txt",
		}[self]


class Attributes(list):
	def __init__(self, value: list | str) -> None:
		if isinstance(value, str):
			from opsicli.io import get_separated_entries  # Avoid circular import

			value = get_separated_entries(value)
		super().__init__(value)


class Bool:
	click_type = bool

	def __new__(cls: type[Bool], value: Any) -> bool:
		if isinstance(value, str):
			value = value.lower() in ("1", "true", "yes")
		return bool(value)


class OPSIServiceUrl(str):
	def __new__(cls: type[OPSIServiceUrl], value: str) -> OPSIServiceUrl:
		value = str(value)
		if "://" not in value:
			value = f"https://{value}"
		url = urlparse(value)
		hostname = str(url.hostname)
		if ":" in hostname:
			hostname = f"[{hostname}]"
		value = f"{url.scheme}://{hostname}:{url.port or 4447}{url.path}"
		return super().__new__(cls, value)


class OPSIServiceUrlOrServiceName(str):
	def __new__(cls: type[OPSIServiceUrlOrServiceName], value: str) -> OPSIServiceUrl | str:
		if value.startswith("http://") or value.startswith("https://"):
			return OPSIServiceUrl(value)
		return value


class Password(str):
	def __new__(cls: type[Password], value: str | None) -> Password:
		return super().__new__(cls, value or "")

	def __repr__(self) -> str:
		return "***secret***"

	def to_yaml(self) -> str | None:
		if not self:
			return None
		return encrypt(str(self))

	@classmethod
	def from_yaml(cls, value: str) -> Password:
		return cls(decrypt(value))


class File(Path):
	click_type = click.Path(dir_okay=False)

	@classmethod
	def cwd(cls) -> Path:
		return Path(os.getcwd())

	def __new__(cls: type[File], *args: Any, **kwargs: Any) -> type[Path]:
		path = Path(*args, **kwargs)
		if str(path) != "-":
			path = path.expanduser().absolute()
			if path.exists() and not path.is_file():
				raise ValueError(f"Not a file: {path!r}")
		return path  # ty: ignore[invalid-return-type]

	def to_yaml(self) -> str:
		return str(self)


class Directory(Path):
	click_type = click.Path(file_okay=False)

	def __new__(cls: type[Directory], *args: Any, **kwargs: Any) -> type[Path]:
		path = Path(*args, **kwargs).expanduser().absolute()
		if path.exists() and not path.is_dir():
			raise ValueError(f"Not a directory: {path!r}")
		return path  # ty: ignore[invalid-return-type]

	def to_yaml(self) -> str:
		return str(self)


@dataclass
class OPSIService:
	name: str
	url: str
	username: str | None = None
	password: Password | None = None
	session_lifetime: int = DEFAULT_SESSION_LIFETIME

	def __setattr__(self, name: str, value: Any) -> None:
		if name == "password" and not isinstance(value, Password):
			value = Password(value)
		self.__dict__[name] = value

	def to_yaml(self) -> dict[str, Any]:
		return {key: val.to_yaml() if hasattr(val, "to_yaml") else val for key, val in vars(self).items()}

	@classmethod
	def from_yaml(cls, value: dict[str, Any]) -> OPSIService:
		if value.get("password"):
			value["password"] = Password.from_yaml(value["password"])
		return cls(**value)


class OpsiCliRuntimeError(RuntimeError):
	pass
