"""Owns the download queue: enforces max-concurrent-downloads, starts the
next queued task whenever a slot frees up, and exposes queue controls."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from backend.progress import DownloadProgress
from backend.ytdlp_backend import YtdlpBackend
from download.task import DownloadStatus, DownloadTask
from download.worker import DownloadWorker

logger = logging.getLogger("ytdlp_gui")

DEFAULT_MAX_CONCURRENT = 2

# How long closing the app waits, in total, for cancelled downloads to stop.
# yt-dlp only checks for cancellation when it reports progress, so a download
# stuck in an FFmpeg merge or a stalled socket can't react until that ends;
# waiting unboundedly would freeze the window on close.
SHUTDOWN_TIMEOUT_MS = 3000


@dataclass
class _ActiveDownload:
    thread: QThread
    worker: DownloadWorker
    cancel_event: threading.Event


class DownloadManager(QObject):
    task_added = Signal(object)
    task_updated = Signal(object)
    task_removed = Signal(str)
    queue_changed = Signal()

    def __init__(self, backend: YtdlpBackend | None = None, max_concurrent: int = DEFAULT_MAX_CONCURRENT) -> None:
        super().__init__()
        self._backend = backend or YtdlpBackend()
        self._max_concurrent = max(1, max_concurrent)
        self._tasks: dict[str, DownloadTask] = {}
        self._order: list[str] = []
        self._pending: list[str] = []
        self._active: dict[str, _ActiveDownload] = {}
        self._remove_when_finished: set[str] = set()
        self._orphaned: list[_ActiveDownload] = []  # still running after a timed-out shutdown
        self._shutting_down = False

    def set_max_concurrent(self, value: int) -> None:
        self._max_concurrent = max(1, value)
        self._try_start_next()

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    def get_task(self, task_id: str) -> DownloadTask | None:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[DownloadTask]:
        return [self._tasks[tid] for tid in self._order]

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def has_orphaned_threads(self) -> bool:
        """True if a download thread was still running when shutdown() gave
        up waiting. The caller should then exit the process without normal
        interpreter teardown, since Qt aborts if a running QThread is
        destroyed (see app/main.py).
        """
        self._orphaned = [a for a in self._orphaned if a.thread.isRunning()]
        return bool(self._orphaned)

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
            # A live QThread can't be torn down from here: cancel it, and
            # finish the removal once the worker reports back.
            self._remove_when_finished.add(task_id)
            self.cancel(task_id)
            return
        self._remove_now(task_id)

    def _remove_now(self, task_id: str) -> None:
        self._remove_when_finished.discard(task_id)
        if task_id in self._pending:
            self._pending.remove(task_id)
        if task_id in self._order:
            self._order.remove(task_id)
        self._tasks.pop(task_id, None)
        self.task_removed.emit(task_id)
        self.queue_changed.emit()

    def _remove_if_requested(self, task_id: str) -> None:
        if task_id in self._remove_when_finished:
            self._remove_now(task_id)

    def move_up(self, task_id: str) -> None:
        self._reorder(task_id, offset=-1)

    def move_down(self, task_id: str) -> None:
        self._reorder(task_id, offset=1)

    def _reorder(self, task_id: str, offset: int) -> None:
        if task_id not in self._pending:
            return
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

    def shutdown(self, timeout_ms: int = SHUTDOWN_TIMEOUT_MS) -> None:
        """Cancel all downloads and wait up to `timeout_ms` in total (one
        shared budget, not per download) for them to stop. Any that haven't
        stopped by then are left running and reported by
        has_orphaned_threads; nothing new is started afterwards. Safe to
        call more than once.
        """
        self._shutting_down = True
        self._pending.clear()

        active_downloads = list(self._active.values())
        for active in active_downloads:
            active.cancel_event.set()

        deadline = time.monotonic() + timeout_ms / 1000
        for active in active_downloads:
            # quit() before run() returns makes the thread's event loop exit
            # as soon as it does, so wait() ends the moment the download
            # notices the cancellation.
            active.thread.quit()
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if not active.thread.wait(remaining_ms):
                logger.warning("A download did not stop within the shutdown timeout; leaving it running.")
                self._orphaned.append(active)
        self._active.clear()

    def _try_start_next(self) -> None:
        if self._shutting_down:
            return
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
        self._remove_if_requested(task_id)
        self._try_start_next()

    def _on_failed(self, task_id: str, user_message: str, technical_detail: str) -> None:
        task = self._finish_active(task_id)
        if task is None:
            return
        task.status = DownloadStatus.FAILED
        task.error_message = user_message
        logger.warning("Task %s failed: %s", task_id, technical_detail)
        self.task_updated.emit(task)
        self._remove_if_requested(task_id)
        self._try_start_next()

    def _on_cancelled(self, task_id: str) -> None:
        task = self._finish_active(task_id)
        if task is None:
            return
        task.status = DownloadStatus.CANCELLED
        self.task_updated.emit(task)
        self._remove_if_requested(task_id)
        self._try_start_next()

    def _finish_active(self, task_id: str) -> DownloadTask | None:
        active = self._active.pop(task_id, None)
        if active is None:
            # Not (or no longer) running, e.g. a late event from a thread
            # orphaned by shutdown(). Ignore it rather than resurrect state.
            return None
        active.thread.quit()
        active.thread.wait()
        return self._tasks.get(task_id)
