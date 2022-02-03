"""
opsi-cli Basic command line interface for opsi

general configuration
"""
import shutil
from functools import lru_cache
from pathlib import Path
import tempfile
import platform

from opsicommon.utils import Singleton  # type: ignore[import]


@lru_cache(maxsize=1)
def get_python_path() -> str:
	for pyversion in ("python3", "python"):
		result = shutil.which(pyversion)
		if result:
			return result
	raise RuntimeError("Could not find python path")


class Config(metaclass=Singleton):
	def __init__(self, **kwargs) -> None:
		self.set_defaults()
		for key, value in kwargs.items():
			self.set_value(key, value)

	def set_defaults(self):
		if platform.system().lower() == "windows":
			# TODO: use a temporary directory to store plugins (Permission issue)
			self.cli_base_dir = Path(tempfile.gettempdir()) / "opsicli"
		else:
			self.cli_base_dir = Path.home() / ".local" / "lib" / "opsicli"
		self.plugin_dir = self.cli_base_dir / "plugins"
		self.lib_dir = self.cli_base_dir / "lib"

	def set_value(self, key, value):
		if not hasattr(self, key):
			raise AttributeError(f"Trying to set invalid config key {key}")
		setattr(self, key, value)


config = Config()
