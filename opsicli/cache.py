# -*- coding: utf-8 -*-
"""
opsi-cli Basic command line interface for opsi

general configuration
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import orjson
from opsicommon.logging import logger  # type: ignore[import]
from opsicommon.utils import Singleton  # type: ignore[import]

from opsicli.config import config


class Cache(metaclass=Singleton):  # pylint: disable=too-few-public-methods
	def __init__(self) -> None:
		self._cache_file: Path = config.user_lib_dir / "cache.json"
		self._data: Dict[str, Any] = {}
		self._loaded = False
		self._modified = False

	def _ensure_loaded(self):
		if not self._loaded:
			self.load()

	def exit(self):
		logger.debug("Cache exit")
		if self._modified:
			self.store()

	def load(self):
		if self._cache_file.exists():
			with open(self._cache_file, "rb") as file:
				try:
					self._data = orjson.loads(file.read()) or {}  # pylint: disable=no-member
				except orjson.JSONDecodeError:  # pylint: disable=no-member
					self._data = {}
		self._loaded = True
		self._modified = False

	def store(self):
		self._ensure_loaded()
		with open(self._cache_file, "wb") as file:
			self._cache_file.chmod(0o600)
			file.write(orjson.dumps(self._data))  # pylint: disable=no-member
		self._modified = False

	def get(self, name: str, default: Optional[Any] = None) -> Any:
		self._ensure_loaded()
		if name not in self._data:
			return default
		if self.ttl_exceeded(name):
			del self._data[name]
			return default
		return self._data[name]["value"]

	def set(self, name: str, value: Any, ttl: int = 0, store: Optional[bool] = False) -> None:
		self._ensure_loaded()
		self._data[name] = {"date": datetime.utcnow().isoformat(), "ttl": max(int(ttl), 0), "value": value}
		self._modified = True
		if store:
			self.store()

	def ttl_exceeded(self, name: str) -> bool:
		return 0 < self._data[name]["ttl"] < self.age(name)

	def age(self, name: str) -> int:
		self._ensure_loaded()
		if name not in self._data:
			return 500_000_000  # ~ 15 years
		return int((datetime.utcnow() - datetime.fromisoformat(self._data[name]["date"])).total_seconds())


cache = Cache()
