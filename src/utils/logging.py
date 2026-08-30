"""Application logging configuration.

Sensitive data (cookies, credentials, auth headers) must NEVER be passed to
these loggers. Call sites are responsible for redacting such values before
logging; see backend/ytdlp_backend.py for the redaction helper once added.
"""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_file: Path, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("ytdlp_gui")
    logger.setLevel(level)

    if logger.handlers:
        # Avoid duplicate handlers if called more than once (e.g. in tests).
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
