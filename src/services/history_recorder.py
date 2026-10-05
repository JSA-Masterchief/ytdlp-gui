"""Listens to DownloadManager task updates and records each finished task
into the persistent HistoryStore exactly once. Kept separate from
DownloadManager itself so the manager doesn't need to know history exists
— it just reports task state, and this is the thing that cares.
"""

from __future__ import annotations

from PySide6.QtCore import QObject

from download.history import HistoryEntry, HistoryStore
from download.manager import DownloadManager
from download.task import DownloadStatus, DownloadTask

_STATUS_MAP = {
    DownloadStatus.COMPLETED: "completed",
    DownloadStatus.FAILED: "failed",
    DownloadStatus.CANCELLED: "cancelled",
}


class HistoryRecorder(QObject):
    """A QObject, deliberately — not just for Qt's parent/child ownership
    option below, but because a plain Python object connected to a signal
    has no guaranteed lifetime: if nothing else holds a strong reference
    to it, it can be garbage collected right after construction (the
    signal connection alone does not reliably keep it alive), silently
    turning off history recording with no error anywhere. Pass `parent`
    to tie this object's lifetime to another QObject (e.g. the main
    window) as an extra safety net; the caller should still keep its own
    reference too.
    """

    def __init__(self, manager: DownloadManager, store: HistoryStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._store = store
        self._recorded_ids: set[str] = set()
        manager.task_updated.connect(self._on_task_updated)

    def _on_task_updated(self, task: DownloadTask) -> None:
        if not task.is_finished or task.id in self._recorded_ids:
            return
        self._recorded_ids.add(task.id)

        entry = HistoryEntry.now(
            url=task.url,
            title=task.display_title,
            status=_STATUS_MAP.get(task.status, "unknown"),
            file_path=task.destination_path,
            format_description=task.selection.quality if task.selection else None,
        )
        self._store.add(entry)
