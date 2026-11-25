"""Runs yt-dlp analysis off the GUI thread and reports results via signals."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal

from backend.models import MediaInfo, PlaylistInfo
from backend.ytdlp_backend import YtdlpBackend, YtdlpBackendError

logger = logging.getLogger("ytdlp_gui")


class AnalysisWorker(QObject):
    finished = Signal(object)
    failed = Signal(str, str)

    def __init__(self, backend: YtdlpBackend, url: str) -> None:
        super().__init__()
        self._backend = backend
        self._url = url

    def run(self) -> None:
        try:
            result = self._backend.analyze(self._url)
        except YtdlpBackendError as exc:
            logger.warning("Analysis failed for %s: %s", self._url, exc.technical_detail)
            self.failed.emit(exc.user_message, exc.technical_detail)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error analyzing %s", self._url)
            self.failed.emit("An unexpected error occurred.", str(exc))
            return

        self.finished.emit(result)


class MetadataService(QObject):
    analysis_finished = Signal(str, object)
    analysis_failed = Signal(str, str, str)

    def __init__(self, backend: YtdlpBackend | None = None) -> None:
        super().__init__()
        self._backend = backend or YtdlpBackend()
        self._cache: dict[str, MediaInfo | PlaylistInfo] = {}
        self._thread: QThread | None = None
        self._worker: AnalysisWorker | None = None
        self._current_url: str | None = None

    def analyze(self, url: str, use_cache: bool = True) -> None:
        if use_cache and url in self._cache:
            self.analysis_finished.emit(url, self._cache[url])
            return

        if self._thread is not None and self._thread.isRunning():
            logger.info("Analysis already in progress; ignoring new request for %s", url)
            return

        self._current_url = url
        self._thread = QThread()
        self._worker = AnalysisWorker(self._backend, url)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._thread.start()

    def _on_finished(self, result: MediaInfo | PlaylistInfo) -> None:
        url = self._current_url
        self._shutdown_thread()
        if url:
            self._cache[url] = result
            self.analysis_finished.emit(url, result)

    def _on_failed(self, user_message: str, technical_detail: str) -> None:
        url = self._current_url
        self._shutdown_thread()
        if url:
            self.analysis_failed.emit(url, user_message, technical_detail)

    def _shutdown_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None

    def clear_cache(self) -> None:
        self._cache.clear()
