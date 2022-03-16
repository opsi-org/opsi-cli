# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

general configuration
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import orjson
from opsicommon.utils import Singleton  # type: ignore[import]

from opsicli.config import config


class Cache(metaclass=Singleton):  # pylint: disable=too-few-public-methods
	def __init__(self) -> None:
		self._cache_file: Path = config.user_lib_dir / "cache.json"
		self._data: Dict[str, Any] = {}
		self._loaded = False

	def _ensure_loaded(self):
		if not self._loaded:
			self.load()

	def load(self):
		if self._cache_file.exists():
			with open(self._cache_file, "rb") as file:
				try:
					self._data = orjson.loads(file.read()) or {}  # pylint: disable=no-member
				except orjson.JSONDecodeError:  # pylint: disable=no-member
					self._data = {}
		self._loaded = True

	def store(self):
		self._ensure_loaded()
		with open(self._cache_file, "wb") as file:
			file.write(orjson.dumps(self._data))  # pylint: disable=no-member

	def get(self, name: str, default: Any) -> Any:
		self._ensure_loaded()
		if name not in self._data:
			return default
		return self._data[name]["value"]

	def set(self, name: str, value: Any, store: Optional[bool] = False) -> None:
		self._ensure_loaded()
		self._data[name] = {"date": datetime.utcnow().isoformat(), "value": value}
		if store:
			self.store()

	def age(self, name: str) -> timedelta:
		self._ensure_loaded()
		if name not in self._data:
			return timedelta(days=1000)
		return datetime.utcnow() - datetime.fromisoformat(self._data[name]["date"])


cache = Cache()
