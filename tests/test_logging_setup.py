from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from utils.logging import configure_logging


@pytest.fixture
def clean_logger():
    """configure_logging mutates the shared 'ytdlp_gui' logger; restore it
    afterwards (closing file handlers) so other tests are unaffected.
    """
    logger = logging.getLogger("ytdlp_gui")
    saved_handlers, saved_level = list(logger.handlers), logger.level
    for handler in saved_handlers:
        logger.removeHandler(handler)
    yield logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    for handler in saved_handlers:
        logger.addHandler(handler)
    logger.setLevel(saved_level)


def _flush(logger):
    for handler in logger.handlers:
        handler.flush()


def test_writes_messages_to_the_log_file(tmp_path, clean_logger):
    log_file = tmp_path / "app.log"
    logger = configure_logging(log_file, level=logging.INFO)

    logger.info("hello from the test")
    _flush(logger)

    text = log_file.read_text(encoding="utf-8")
    assert "hello from the test" in text
    assert "[INFO]" in text


def test_respects_the_configured_level(tmp_path, clean_logger):
    log_file = tmp_path / "app.log"
    logger = configure_logging(log_file, level=logging.WARNING)

    logger.info("too quiet")
    logger.warning("loud enough")
    _flush(logger)

    text = log_file.read_text(encoding="utf-8")
    assert "too quiet" not in text
    assert "loud enough" in text


def test_calling_twice_does_not_duplicate_handlers_or_lines(tmp_path, clean_logger):
    log_file = tmp_path / "app.log"
    configure_logging(log_file)
    logger = configure_logging(log_file)

    assert len(logger.handlers) == 2  # one file, one console

    logger.info("only once")
    _flush(logger)
    assert log_file.read_text(encoding="utf-8").count("only once") == 1


def test_returns_the_named_application_logger(tmp_path, clean_logger):
    assert configure_logging(tmp_path / "app.log").name == "ytdlp_gui"


def test_log_file_is_utf8_safe(tmp_path, clean_logger):
    log_file = tmp_path / "app.log"
    logger = configure_logging(log_file)

    logger.info("título — 動画 ✓")
    _flush(logger)

    assert "título — 動画 ✓" in log_file.read_text(encoding="utf-8")
