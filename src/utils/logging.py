"""Application logging configuration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def configure_logging(log_file: Path, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("ytdlp_gui")
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # A windowed (no-console) PyInstaller build has no stderr at all.
    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
