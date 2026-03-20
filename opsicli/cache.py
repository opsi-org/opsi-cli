# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
opsi-cli Basic command line interface for opsi

general configuration
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson
from opsicommon.logging import get_logger

from opsicli.config import config
from opsicli.singelton import Singleton

logger = get_logger("opsicli")


class Cache(metaclass=Singleton):
	def __init__(self) -> None:
		self._cache_file: Path = config.user_lib_dir / "cache.json"
		self._data: dict[str, Any] = {}
		self._loaded = False
		self._modified = False

	def _ensure_loaded(self) -> None:
		if not self._loaded:
			self.load()

	def exit(self) -> None:
		logger.debug("Cache exit")
		if self._modified:
			self.store()

	def load(self) -> None:
		if self._cache_file.exists():
			with open(self._cache_file, "rb") as file:
				try:
					self._data = orjson.loads(file.read()) or {}
				except orjson.JSONDecodeError:
					self._data = {}
		self._loaded = True
		self._modified = False

	def store(self) -> None:
		self._ensure_loaded()
		if not self._cache_file.parent.exists():
			self._cache_file.parent.mkdir(parents=True)
		with open(self._cache_file, "wb") as file:
			self._cache_file.chmod(0o600)
			file.write(orjson.dumps(self._data))
		self._modified = False

	def clear(self) -> None:
		self._cache_file.unlink(missing_ok=True)
		self._data = {}
		self._loaded = False
		self._modified = False

	def get(self, name: str, default: Any = None) -> Any:
		self._ensure_loaded()
		if name not in self._data:
			return default
		if self.ttl_exceeded(name):
			self.delete(name)
			return default
		return self._data[name]["value"]

	def set(self, name: str, value: Any, ttl: int = 0, store: bool = False) -> None:
		self._ensure_loaded()
		self._data[name] = {"date": datetime.now(tz=timezone.utc).isoformat(), "ttl": max(int(ttl), 0), "value": value}
		self._modified = True
		if store:
			self.store()

	def delete(self, name: str, store: bool = False) -> None:
		self._ensure_loaded()
		if name not in self._data:
			return
		del self._data[name]
		self._modified = True
		if store:
			self.store()

	def ttl_exceeded(self, name: str) -> bool:
		return 0 < self._data[name]["ttl"] < self.age(name)

	def age(self, name: str) -> int:
		self._ensure_loaded()
		if name not in self._data:
			return 500_000_000  # ~ 15 years
		iso_date = self._data[name]["date"]
		if "+" not in iso_date:
			iso_date += "+00:00"
		return int((datetime.now(tz=timezone.utc) - datetime.fromisoformat(iso_date)).total_seconds())


cache = Cache()
