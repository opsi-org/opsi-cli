# -*- coding: utf-8 -*-
"""
opsi-cli - command line interface for opsi

types
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import rich_click as click  # type: ignore[import]
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

	def __new__(cls, value: Any):
		try:
			value = min(9, max(0, int(value)))
		except ValueError:
			try:
				value = LEVEL_TO_OPSI_LEVEL[NAME_TO_LEVEL[value.upper()]]
			except KeyError:
				raise ValueError(f"{value!r} is not a valid log level, choose one of: {cls.possible_values_for_description}") from None
		return super().__new__(cls, value)

	def to_yaml(self):
		return int(self)


class OutputFormat(str):
	possible_values = ["auto", "json", "pretty-json", "msgpack", "table", "csv"]
	possible_values_for_description = ", ".join([f"[metavar]{v}[/metavar]" for v in possible_values])

	def __new__(cls, value: Any):
		value = str(value)
		if value not in cls.possible_values:
			raise ValueError(f"{value!r} is not a valid output format, choose one of: {cls.possible_values_for_description}") from None
		return super().__new__(cls, value)

	def to_yaml(self):
		return str(self)


class Attributes(list):
	def __init__(self, value):
		if isinstance(value, str):
			value = [v.strip() for v in value.split(",") if v.strip()]
		super().__init__(value)


class Bool:  # pylint: disable=too-few-public-methods
	click_type = bool

	def __new__(cls, value: Any):
		if isinstance(value, str):
			value = value.lower() in ("1", "true", "yes")
		return bool(value)


class OPSIServiceUrl(str):  # pylint: disable=too-few-public-methods
	def __new__(cls, value: Any):
		value = str(value)
		if "://" not in value:
			value = f"https://{value}"
		url = urlparse(value)
		hostname = str(url.hostname)
		if ":" in hostname:
			hostname = f"[{hostname}]"
		value = f"{url.scheme}://{hostname}:{url.port or 4447}{url.path}"
		return super().__new__(cls, value)


class OPSIServiceUrlOrServiceName(str):  # pylint: disable=too-few-public-methods
	def __new__(cls, value: Any):
		if value.startswith("http://") or value.startswith("https://"):
			return OPSIServiceUrl(value)
		return value


class Password(str):  # pylint: disable=too-few-public-methods
	def __new__(cls, value: Any):
		if value is None:
			return None
		return super().__new__(cls, value)

	def __repr__(self):
		return "***secret***"

	def to_yaml(self):
		if not self:
			return self
		return encrypt(str(self))

	@classmethod
	def from_yaml(cls, value):
		return cls(decrypt(value))


class File(type(Path())):  # type: ignore[misc] # pylint: disable=too-few-public-methods
	click_type = click.Path(dir_okay=False)

	def __new__(cls, *args, **kwargs):
		path = super().__new__(cls, *args, **kwargs)
		if str(path) != "-":
			path = path.expanduser().absolute()
			if path.exists() and not path.is_file():
				raise ValueError("Not a file: {path!r}")
		return path

	def to_yaml(self):
		return str(self)


class Directory(type(Path())):  # type: ignore[misc] # pylint: disable=too-few-public-methods
	click_type = click.Path(file_okay=False)

	def __new__(cls, *args, **kwargs):
		path = super().__new__(cls, *args, **kwargs)
		path = path.expanduser().absolute()
		if path.exists() and not path.is_dir():
			raise ValueError("Not a directory: {path!r}")
		return path

	def to_yaml(self):
		return str(self)


@dataclass
class OPSIService:
	name: str
	url: str
	username: Optional[str] = None
	password: Optional[Password] = None

	def __setattr__(self, name: str, value: Any) -> None:
		if name == "password" and not isinstance(value, Password):
			value = Password(value)
		self.__dict__[name] = value

	def to_yaml(self):
		return {key: val.to_yaml() if hasattr(val, "to_yaml") else val for key, val in vars(self).items()}

	@classmethod
	def from_yaml(cls, value):
		if value.get("password"):
			value["password"] = Password.from_yaml(value["password"])
		return cls(**value)
