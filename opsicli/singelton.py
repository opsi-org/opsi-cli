from __future__ import annotations

from typing import Any


class Singleton(type):
	_instances: dict[type, type] = {}

	def __call__(cls: Singleton, *args: Any, **kwargs: Any) -> type:
		if cls not in cls._instances:
			cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
		return cls._instances[cls]
