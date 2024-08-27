# -*- coding: utf-8 -*-
"""
This module provides utility functions for temporary files and directories.
"""

import shutil
import tempfile
from pathlib import Path

from opsicommon.logging import get_logger

logger = get_logger("opsicli")


class TempDirManager:
	"""
	Manages a temporary directory.
	"""

	def __init__(self) -> None:
		self._temp_dir_path: Path | None = None

	def get_temp_dir(self) -> Path:
		"""
		Get or create the temporary directory.
		"""
		if self._temp_dir_path is None:
			try:
				self._temp_dir_path = Path(tempfile.mkdtemp())
				logger.info("Created temporary directory %s", self._temp_dir_path)
			except Exception as err:
				raise RuntimeError(f"Failed to create temporary directory: {err}") from err
		return self._temp_dir_path

	def delete_temp_dir(self) -> None:
		"""
		Delete the temporary directory and its contents.
		"""
		if self._temp_dir_path and self._temp_dir_path.exists():
			try:
				shutil.rmtree(self._temp_dir_path)
				logger.info("Deleted temporary directory %s", self._temp_dir_path)
			except Exception as err:
				raise RuntimeError(f"Failed to delete temporary directory: {err}") from err
			finally:
				self._temp_dir_path = None
