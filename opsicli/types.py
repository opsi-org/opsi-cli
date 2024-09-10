# -*- coding: utf-8 -*-
"""
opsi-cli - command line interface for opsi

types
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Type
from urllib.parse import urlparse

from opsicli.config import COMPLETION_MODE

if not COMPLETION_MODE:  # type: ignore[has-type]
	import rich_click as click  # type: ignore[import]
else:
	# Loads faster
	import click  # type: ignore[import,no-redef]

from opsicommon.logging import (  # type: ignore[import]
	LEVEL_TO_OPSI_LEVEL,
	NAME_TO_LEVEL,
)

from opsicli.utils import decrypt, encrypt


class LogLevel(int):
	possible_values = list(reversed([v.lower() for v in NAME_TO_LEVEL]))
	possible_values_for_description = ", ".join(
		[f"[metavar]{name}[/metavar]/[metavar]{LEVEL_TO_OPSI_LEVEL[NAME_TO_LEVEL[name.upper()]]}[/metavar]" for name in possible_values]
	)

	def __new__(cls, value: Any) -> LogLevel:
		try:
			value = min(9, max(0, int(value)))
		except ValueError:
			try:
				value = LEVEL_TO_OPSI_LEVEL[NAME_TO_LEVEL[value.upper()]]
			except KeyError:
				raise ValueError(f"{value!r} is not a valid log level, choose one of: {cls.possible_values_for_description}") from None
		return super().__new__(cls, value)

	def to_yaml(self) -> int:
		return int(self)


class OutputFormat(str):
	possible_values = ["auto", "json", "pretty-json", "msgpack", "table", "csv"]
	possible_values_for_description = ", ".join([f"[metavar]{v}[/metavar]" for v in possible_values])

	def __new__(cls: Type[OutputFormat], value: Any) -> OutputFormat:
		value = str(value)
		if value not in cls.possible_values:
			raise ValueError(f"{value!r} is not a valid output format, choose one of: {cls.possible_values_for_description}") from None
		return super().__new__(cls, value)

	def to_yaml(self) -> str:
		return str(self)


class Attributes(list):
	def __init__(self, value: list | str) -> None:
		if isinstance(value, str):
			value = [v.strip() for v in value.split(",") if v.strip()]
		super().__init__(value)


class Bool:
	click_type = bool

	def __new__(cls: Type[Bool], value: Any) -> bool:  # type: ignore[misc]
		if isinstance(value, str):
			value = value.lower() in ("1", "true", "yes")
		return bool(value)


class OPSIServiceUrl(str):
	def __new__(cls: Type[OPSIServiceUrl], value: str) -> OPSIServiceUrl:
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
	def __new__(cls: Type[OPSIServiceUrlOrServiceName], value: str) -> OPSIServiceUrl | str:  # type: ignore[misc]
		if value.startswith("http://") or value.startswith("https://"):
			return OPSIServiceUrl(value)
		return value


class Password(str):
	def __new__(cls: Type[Password], value: str | None) -> Password:
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


class File(type(Path())):  # type: ignore[misc] # pylint: disable=too-few-public-methods
	click_type = click.Path(dir_okay=False)

	@classmethod
	def cwd(cls) -> Path:
		return Path(os.getcwd())

	def __new__(cls: Type[File], *args: Any, **kwargs: Any) -> File:
		path = super().__new__(cls, *args, **kwargs)
		if str(path) != "-":
			path = path.expanduser().absolute()
			if path.exists() and not path.is_file():
				raise ValueError(f"Not a file: {path!r}")
		return path

	def to_yaml(self) -> str:
		return str(self)


class Directory(type(Path())):  # type: ignore[misc] # pylint: disable=too-few-public-methods
	click_type = click.Path(file_okay=False)

	def __new__(cls: Type[Directory], *args: Any, **kwargs: Any) -> Directory:
		path = super().__new__(cls, *args, **kwargs)
		path = path.expanduser().absolute()
		if path.exists() and not path.is_dir():
			raise ValueError(f"Not a directory: {path!r}")
		return path

	def to_yaml(self) -> str:
		return str(self)


@dataclass
class OPSIService:
	name: str
	url: str
	username: str | None = None
	password: Password | None = None

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
