# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

types
"""

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from opsicommon.logging import (  # type: ignore[import]
	LEVEL_TO_OPSI_LEVEL,
	NAME_TO_LEVEL,
)


class LogLevel(int):
	possible_values = reversed([v.lower() for v in NAME_TO_LEVEL])
	possible_values_for_description = ", ".join([f"{name}/{LEVEL_TO_OPSI_LEVEL[NAME_TO_LEVEL[name.upper()]]}" for name in possible_values])

	def __new__(cls, value: Any):
		try:
			value = min(9, max(0, int(value)))
		except ValueError:
			try:
				value = LEVEL_TO_OPSI_LEVEL[NAME_TO_LEVEL[value.upper()]]
			except KeyError:
				raise ValueError(f"{value!r} is not a valid log level, choose one of: {cls.possible_values_for_description}") from None
		return super().__new__(cls, value)


class OutputFormat(str):
	possible_values = ["auto", "json", "pretty-json", "msgpack", "table", "csv"]
	possible_values_for_description = ", ".join(possible_values)

	def __new__(cls, value: Any):
		value = str(value)
		if value not in cls.possible_values:
			raise ValueError(f"{value!r} is not a valid output format, choose one of: {cls.possible_values_for_description}") from None
		return super().__new__(cls, value)


class Attributes(list):
	def __init__(self, value):
		if isinstance(value, str):
			value = [v.strip() for v in value.split(",") if v.strip()]
		super().__init__(value)


class Bool:  # pylint: disable=too-few-public-methods
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


class Password(str):  # pylint: disable=too-few-public-methods
	def __new__(cls, value: Any):
		return super().__new__(cls, value)

	def __repr__(self):
		return "***secret***"


class File(type(Path())):  # type: ignore[misc] # pylint: disable=too-few-public-methods
	def __new__(cls, *args, **kwargs):
		path = super().__new__(cls, *args, **kwargs)
		if str(path) != "-":
			path = path.expanduser().absolute()
			if path.exists() and not path.is_file():
				raise ValueError("Not a file: {path!r}")
		return path


class Directory(type(Path())):  # type: ignore[misc] # pylint: disable=too-few-public-methods
	def __new__(cls, *args, **kwargs):
		path = super().__new__(cls, *args, **kwargs)
		path = path.expanduser().absolute()
		if path.exists() and not path.is_dir():
			raise ValueError("Not a directory: {path!r}")
		return path
