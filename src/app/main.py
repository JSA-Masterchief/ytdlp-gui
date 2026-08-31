"""Application entry point.

Run with: python src/app/main.py
(src/ is added to sys.path so `app.*`, `ui.*` etc. resolve as top-level
packages — see the sys.path shim below.)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Allow running this file directly (python src/app/main.py) by ensuring
# src/ is importable as the package root.
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

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
