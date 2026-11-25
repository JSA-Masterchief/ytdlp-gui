"""Runs a single download on its own QThread and reports progress/outcome
via signals."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal

from backend.progress import DownloadCancelRequested, DownloadProgress
from backend.ytdlp_backend import DownloadCancelledError, YtdlpBackend, YtdlpBackendError

logger = logging.getLogger("ytdlp_gui")


class DownloadWorker(QObject):
    progress = Signal(object)
    succeeded = Signal()
    failed = Signal(str, str)
    cancelled = Signal()

    def __init__(
        self,
        backend: YtdlpBackend,
        url: str,
        options: dict,
        cancel_event: threading.Event,
        task_id: str = "",
    ) -> None:
        super().__init__()
        self._backend = backend
        self._url = url
        self._options = options
        self._cancel_event = cancel_event
        self.task_id = task_id

    def run(self) -> None:
        def progress_callback(progress: DownloadProgress) -> None:
            if self._cancel_event.is_set():
                raise DownloadCancelRequested("Cancelled by user")
            self.progress.emit(progress)

        try:
            self._backend.download(self._url, self._options, progress_callback=progress_callback)
        except DownloadCancelledError:
            self.cancelled.emit()
            return
        except YtdlpBackendError as exc:
            logger.warning("Download failed for %s: %s", self._url, exc.technical_detail)
            self.failed.emit(exc.user_message, exc.technical_detail)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error downloading %s", self._url)
            self.failed.emit("An unexpected error occurred.", str(exc))
            return

        self.succeeded.emit()
