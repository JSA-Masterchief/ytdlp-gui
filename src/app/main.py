"""Application entry point."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Must run before anything imports yt_dlp, so a downloaded update (newer
# than the bundled copy) is the one that gets loaded.
from backend.ytdlp_updater import activate_override, override_active, running_version  # noqa: E402

_ytdlp_override_error = None
try:
    activate_override()
except Exception as _exc:  # noqa: BLE001 - never let the updater stop startup
    _ytdlp_override_error = _exc

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import load_config  # noqa: E402
from app.constants import APP_NAME  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from utils.logging import configure_logging  # noqa: E402
from utils.paths import get_log_file_path, get_resource_path  # noqa: E402


def main() -> int:
    logger = configure_logging(get_log_file_path(), level=logging.INFO)
    logger.info("Starting %s", APP_NAME)

    config = load_config()
    logger.debug("Loaded config: theme=%s, download_dir=%s", config.theme, config.download_directory)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    icon_path = get_resource_path("assets/icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()

    if _ytdlp_override_error is not None:
        logger.warning("yt-dlp update activation failed: %s", _ytdlp_override_error)
    logger.info(
        "Using yt-dlp %s (%s)",
        running_version(),
        "downloaded update" if override_active() else "built in",
    )
    if config.check_ytdlp_updates:
        QTimer.singleShot(4000, window.check_for_ytdlp_update_quietly)

    exit_code = app.exec()

    if window.download_manager.has_orphaned_threads:
        # A download didn't stop within the shutdown timeout (see
        # DownloadManager.shutdown). Normal interpreter teardown would
        # destroy its still-running QThread, which makes Qt abort with a
        # crash. Partial downloads are resumable, so skip teardown instead.
        logger.warning("Exiting with a download thread still running; skipping normal teardown.")
        logging.shutdown()
        os._exit(exit_code)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
