"""Tests for app.main.main(): startup wiring and, in particular, the
hard-exit path used when a download thread couldn't be stopped.

QApplication, MainWindow, logging setup and os._exit are all mocked — a
real os._exit would kill the test runner, and a second QApplication can't
coexist with pytest-qt's.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import app.main as main_module
from app.config import AppConfig
from app.constants import APP_NAME


def _run_main(has_orphans: bool, exit_code: int = 7):
    fake_window = MagicMock()
    fake_window.download_manager.has_orphaned_threads = has_orphans
    fake_app = MagicMock()
    fake_app.exec.return_value = exit_code
    fake_logger = MagicMock()

    with patch.object(main_module, "configure_logging", return_value=fake_logger), patch.object(
        main_module, "get_log_file_path", return_value=Path("unused.log")
    ), patch.object(main_module, "load_config", return_value=AppConfig()), patch.object(
        main_module, "QApplication", return_value=fake_app
    ), patch.object(main_module, "MainWindow", return_value=fake_window), patch.object(
        main_module.os, "_exit"
    ) as mock_exit, patch.object(main_module.logging, "shutdown") as mock_shutdown:
        result = main_module.main()

    return result, mock_exit, mock_shutdown, fake_window, fake_app, fake_logger


def test_normal_exit_returns_the_event_loop_code_without_hard_exit():
    result, mock_exit, mock_shutdown, _window, _app, _logger = _run_main(has_orphans=False, exit_code=3)

    assert result == 3
    mock_exit.assert_not_called()
    mock_shutdown.assert_not_called()


def test_orphaned_download_thread_triggers_hard_exit_with_the_same_code():
    _result, mock_exit, mock_shutdown, _window, _app, logger = _run_main(has_orphans=True, exit_code=7)

    mock_exit.assert_called_once_with(7)
    mock_shutdown.assert_called_once()  # log handlers flushed before skipping teardown
    logger.warning.assert_called()


def test_window_is_shown_before_the_event_loop_starts():
    _result, _exit, _shutdown, window, app, _logger = _run_main(has_orphans=False)

    window.show.assert_called_once()
    app.exec.assert_called_once()


def test_application_name_is_set():
    _result, _exit, _shutdown, _window, app, _logger = _run_main(has_orphans=False)
    app.setApplicationName.assert_called_once_with(APP_NAME)
