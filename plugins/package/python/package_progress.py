"""
This module provides a progress listener for various package operations using the rich progress bar.
"""

from opsicommon.package.archive import ArchiveProgress, ArchiveProgressListener
from rich.progress import Progress


class PackageProgressListener(ArchiveProgressListener):
	def __init__(self, progress: Progress, task_message: str):
		self.progress = progress
		self.started = False
		self.task_id = self.progress.add_task(task_message, total=None)

	def progress_changed(self, progress: ArchiveProgress) -> None:
		if not self.started:
			self.started = True
			self.progress.tasks[self.task_id].total = 100
		self.progress.update(self.task_id, completed=progress.percent_completed)


class ProgressCallbackAdapter:
	def __init__(self, progress: Progress, task_message: str):
		self.progress = progress
		self.started = False
		self.task_id = self.progress.add_task(task_message, total=None)

	def progress_callback(self, completed: int, total: int) -> None:
		if not self.started:
			self.started = True
			self.progress.tasks[self.task_id].total = total
		self.progress.update(self.task_id, completed=completed)
