# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

types
"""

from urllib.parse import urlparse
from typing import Any
from pathlib import Path

from opsicommon.logging import (  # type: ignore[import]
	NAME_TO_LEVEL,
	LEVEL_TO_OPSI_LEVEL,
)


class LogLevel(int):
	possible_level_names = reversed([v.lower() for v in NAME_TO_LEVEL])
	possible_values_for_description = ", ".join(
		[f"{name}/{LEVEL_TO_OPSI_LEVEL[NAME_TO_LEVEL[name.upper()]]}" for name in possible_level_names]
	)

	def __new__(cls, value: Any):
		try:
			value = min(9, max(0, int(value)))
		except ValueError:
			try:
				value = LEVEL_TO_OPSI_LEVEL[NAME_TO_LEVEL[value.upper()]]
			except KeyError:
				raise ValueError(f"{value!r} is not a valid log level, choose on of: {', '.join(cls.possible_level_names)}") from None
		return super().__new__(cls, value)


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
