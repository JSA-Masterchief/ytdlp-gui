"""Application entry point."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import load_config  # noqa: E402
from app.constants import APP_NAME  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from utils.logging import configure_logging  # noqa: E402
from utils.paths import get_log_file_path  # noqa: E402


def main() -> int:
    logger = configure_logging(get_log_file_path(), level=logging.INFO)
    logger.info("Starting %s", APP_NAME)

    config = load_config()
    logger.debug("Loaded config: theme=%s, download_dir=%s", config.theme, config.download_directory)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    window = MainWindow()
    window.show()

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
