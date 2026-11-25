"""Runs yt-dlp update checks/installs off the UI thread and reports back via
Qt signals (emitted from the worker thread, delivered on the UI thread)."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal

from backend import ytdlp_updater
from backend.ytdlp_updater import Release, UpdateError

logger = logging.getLogger("ytdlp_gui")


class YtdlpUpdateService(QObject):
    # (latest Release or None if already up to date, running version)
    check_finished = Signal(object, str)
    check_failed = Signal(str)
    install_finished = Signal(str)  # installed version
    install_failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._busy

    def running_version(self) -> str:
        try:
            return ytdlp_updater.running_version()
        except Exception:  # noqa: BLE001
            return "unknown"

    def pending_version(self) -> str | None:
        """A downloaded version that will be used after a restart, if it isn't already running."""
        installed = ytdlp_updater.installed_version()
        if installed and installed != self.running_version():
            return installed
        return None

    def _start(self, target, *args) -> bool:  # noqa: ANN001
        with self._lock:
            if self._busy:
                return False
            self._busy = True
        threading.Thread(target=target, args=args, daemon=True, name="ytdlp-updater").start()
        return True

    def check(self) -> bool:
        return self._start(self._check)

    def install(self, release: Release) -> bool:
        return self._start(self._install, release)

    def _check(self) -> None:
        try:
            release = ytdlp_updater.fetch_latest_release()
            newest_known = self.pending_version() or self.running_version()
            if ytdlp_updater.is_newer(release.version, newest_known):
                if not ytdlp_updater.python_supported(release.requires_python):
                    raise UpdateError(
                        f"yt-dlp {release.version} needs a newer app build (Python {release.requires_python})."
                    )
                result = release
            else:
                result = None
        except UpdateError as exc:
            self._busy = False
            self.check_failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error while checking for yt-dlp updates")
            self._busy = False
            self.check_failed.emit(f"Update check failed: {exc}")
            return
        self._busy = False
        self.check_finished.emit(result, self.running_version())

    def _install(self, release: Release) -> None:
        try:
            version = ytdlp_updater.install_release(release)
        except UpdateError as exc:
            self._busy = False
            self.install_failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error while installing yt-dlp %s", release.version)
            self._busy = False
            self.install_failed.emit(f"Update failed: {exc}")
            return
        self._busy = False
        self.install_finished.emit(version)

    def reset_to_bundled(self) -> None:
        ytdlp_updater.reset_to_bundled()
