"""Owns the download queue: enforces max-concurrent-downloads, starts the
next queued task whenever a slot frees up, and exposes the controls the
Queue page needs (cancel, retry, remove, reorder, clear completed).

Threading model: each active download gets its own QThread + DownloadWorker
pair, created fresh per attempt. Thread teardown is always synchronous
(quit() then wait()) before we touch shared state again — see
services/metadata_service.py for the crash this avoids if done any other
way.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from backend.progress import DownloadProgress
from backend.ytdlp_backend import YtdlpBackend
from download.task import DownloadStatus, DownloadTask
from download.worker import DownloadWorker

logger = logging.getLogger("ytdlp_gui")

DEFAULT_MAX_CONCURRENT = 2


@dataclass
class _ActiveDownload:
    thread: QThread
    worker: DownloadWorker
    cancel_event: threading.Event


class DownloadManager(QObject):
    task_added = Signal(object)  # DownloadTask
    task_updated = Signal(object)  # DownloadTask
    task_removed = Signal(str)  # task id
    queue_changed = Signal()

    def __init__(self, backend: YtdlpBackend | None = None, max_concurrent: int = DEFAULT_MAX_CONCURRENT) -> None:
        super().__init__()
        self._backend = backend or YtdlpBackend()
        self._max_concurrent = max(1, max_concurrent)
        self._tasks: dict[str, DownloadTask] = {}
        self._order: list[str] = []  # display order, all tasks
        self._pending: list[str] = []  # queued task ids awaiting a slot
        self._active: dict[str, _ActiveDownload] = {}

    # -- configuration -----------------------------------------------------

    def set_max_concurrent(self, value: int) -> None:
        self._max_concurrent = max(1, value)
        self._try_start_next()

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    # -- queries -------------------------------------------------------------

    def get_task(self, task_id: str) -> DownloadTask | None:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[DownloadTask]:
        return [self._tasks[tid] for tid in self._order]

    @property
    def active_count(self) -> int:
        return len(self._active)

    # -- queue mutation ------------------------------------------------------

    def add_task(self, task: DownloadTask) -> None:
        self._tasks[task.id] = task
        self._order.append(task.id)
        self._pending.append(task.id)
        self.task_added.emit(task)
        self.queue_changed.emit()
        self._try_start_next()

    def cancel(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return

        if task_id in self._active:
            # Cooperative cancellation: the worker's own progress callback
            # checks this flag. It is NOT instantaneous — see download/worker.py.
            self._active[task_id].cancel_event.set()
            return

        if task_id in self._pending:
            self._pending.remove(task_id)
            task.status = DownloadStatus.CANCELLED
            self.task_updated.emit(task)
            self.queue_changed.emit()

    def retry(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None or not task.can_retry:
            return
        task.status = DownloadStatus.QUEUED
        task.error_message = None
        task.progress = None
        if task_id not in self._pending:
            self._pending.append(task_id)
        self.task_updated.emit(task)
        self.queue_changed.emit()
        self._try_start_next()

    def remove(self, task_id: str) -> None:
        if task_id in self._active:
            self.cancel(task_id)
            # Removal completes once the cancelled worker reports back;
            # avoid tearing down a live QThread here.
            return
        if task_id in self._pending:
            self._pending.remove(task_id)
        if task_id in self._order:
            self._order.remove(task_id)
        self._tasks.pop(task_id, None)
        self.task_removed.emit(task_id)
        self.queue_changed.emit()

    def move_up(self, task_id: str) -> None:
        self._reorder(task_id, offset=-1)

    def move_down(self, task_id: str) -> None:
        self._reorder(task_id, offset=1)

    def _reorder(self, task_id: str, offset: int) -> None:
        if task_id not in self._pending:
            return  # only queued (not-yet-started) tasks can be reordered
        idx = self._pending.index(task_id)
        new_idx = idx + offset
        if 0 <= new_idx < len(self._pending):
            self._pending[idx], self._pending[new_idx] = self._pending[new_idx], self._pending[idx]
            self.queue_changed.emit()

    def clear_completed(self) -> None:
        to_remove = [tid for tid in self._order if self._tasks[tid].status == DownloadStatus.COMPLETED]
        for tid in to_remove:
            self._order.remove(tid)
            self._tasks.pop(tid, None)
            self.task_removed.emit(tid)
        if to_remove:
            self.queue_changed.emit()

    def shutdown(self) -> None:
        """Cancel and synchronously join all active downloads. Call this
        before application exit so no QThread is destroyed while running.
        """
        for task_id in list(self._active.keys()):
            self._active[task_id].cancel_event.set()
        for task_id in list(self._active.keys()):
            active = self._active.get(task_id)
            if active is not None:
                active.thread.quit()
                active.thread.wait()
        self._active.clear()

    # -- internal: starting and finishing downloads ---------------------------

    def _try_start_next(self) -> None:
        while self._pending and len(self._active) < self._max_concurrent:
            task_id = self._pending.pop(0)
            task = self._tasks.get(task_id)
            if task is None:
                continue
            self._start_task(task)

    def _start_task(self, task: DownloadTask) -> None:
        task.status = DownloadStatus.DOWNLOADING
        self.task_updated.emit(task)

        cancel_event = threading.Event()
        thread = QThread()
        worker = DownloadWorker(self._backend, task.url, task.ytdlp_options, cancel_event, task_id=task.id)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        # Connected to real bound methods of `self` (a QObject living on the
        # main thread), not lambdas: PySide6 only auto-detects the need for
        # a queued cross-thread connection when the receiver is a QObject
        # method. A lambda has no thread affinity of its own, so Qt (even
        # with an explicit QueuedConnection hint) invokes it directly on
        # the emitting worker thread — which then deadlocks/aborts the
        # moment it calls thread.wait() on its own thread. Each handler
        # below recovers which task it's for via self.sender().
        worker.progress.connect(self._on_worker_progress)
        worker.succeeded.connect(self._on_worker_succeeded)
        worker.failed.connect(self._on_worker_failed)
        worker.cancelled.connect(self._on_worker_cancelled)

        self._active[task.id] = _ActiveDownload(thread=thread, worker=worker, cancel_event=cancel_event)
        thread.start()

    def _on_worker_progress(self, progress: DownloadProgress) -> None:
        worker = self.sender()
        task_id = getattr(worker, "task_id", None)
        if task_id:
            self._on_progress(task_id, progress)

    def _on_worker_succeeded(self) -> None:
        worker = self.sender()
        task_id = getattr(worker, "task_id", None)
        if task_id:
            self._on_succeeded(task_id)

    def _on_worker_failed(self, user_message: str, technical_detail: str) -> None:
        worker = self.sender()
        task_id = getattr(worker, "task_id", None)
        if task_id:
            self._on_failed(task_id, user_message, technical_detail)

    def _on_worker_cancelled(self) -> None:
        worker = self.sender()
        task_id = getattr(worker, "task_id", None)
        if task_id:
            self._on_cancelled(task_id)

    def _on_progress(self, task_id: str, progress: DownloadProgress) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.progress = progress
        if progress.status == "downloading":
            task.status = DownloadStatus.DOWNLOADING
        elif progress.status in ("finished", "post_processing", "processing"):
            task.status = DownloadStatus.POST_PROCESSING
        if progress.filename:
            task.destination_path = progress.filename
        self.task_updated.emit(task)

    def _on_succeeded(self, task_id: str) -> None:
        task = self._finish_active(task_id)
        if task is None:
            return
        task.status = DownloadStatus.COMPLETED
        self.task_updated.emit(task)
        self._try_start_next()

    def _on_failed(self, task_id: str, user_message: str, technical_detail: str) -> None:
        task = self._finish_active(task_id)
        if task is None:
            return
        task.status = DownloadStatus.FAILED
        task.error_message = user_message
        logger.warning("Task %s failed: %s", task_id, technical_detail)
        self.task_updated.emit(task)
        self._try_start_next()

    def _on_cancelled(self, task_id: str) -> None:
        task = self._finish_active(task_id)
        if task is None:
            return
        task.status = DownloadStatus.CANCELLED
        self.task_updated.emit(task)
        self._try_start_next()

    def _finish_active(self, task_id: str) -> DownloadTask | None:
        active = self._active.pop(task_id, None)
        if active is not None:
            # Synchronous join, done here rather than relying on a
            # thread.finished callback, so we never touch a QThread that
            # might still be shutting down. See module docstring.
            active.thread.quit()
            active.thread.wait()
        return self._tasks.get(task_id)
