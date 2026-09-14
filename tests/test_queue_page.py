"""Tests for ui.pages.queue_page.QueuePage.

Uses a real DownloadManager with the real YtdlpBackend, mocking only
yt_dlp.YoutubeDL — same approach as test_download_manager.py — so the page
is exercised against genuine manager signal traffic, not a hand-rolled
fake manager.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QProgressBar, QPushButton

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.ytdlp_backend import YtdlpBackend
from download.manager import DownloadManager
from download.task import DownloadStatus, DownloadTask
from formats.selector import FormatSelection
from ui.pages.queue_page import QueuePage, _format_eta, _format_speed


def _make_task(url: str = "https://example.com/v", title: str | None = None) -> DownloadTask:
    return DownloadTask(
        url=url,
        selection=FormatSelection(),
        output_dir="/tmp/downloads",
        filename_template="%(title)s.%(ext)s",
        ytdlp_options={"format": "best"},
        title=title,
    )


def _controllable_ydl_factory(hold_events: dict[str, threading.Event]):
    def _factory(opts):
        mock_ydl = MagicMock()

        def _download(urls):
            url = urls[0]
            hooks = opts.get("progress_hooks", [])
            for hook in hooks:
                hook({"status": "downloading", "downloaded_bytes": 40, "total_bytes": 100, "speed": 2048.0, "eta": 5})
            hold_events[url].wait(timeout=5)
            for hook in hooks:
                hook({"status": "finished", "filename": f"{url}.mp4"})

        mock_ydl.download.side_effect = _download
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = False
        return mock_ydl

    return _factory


def test_format_speed_and_eta_helpers():
    assert _format_speed(None) == ""
    assert _format_speed(500) == "500 B/s"
    assert _format_speed(2048) == "2 KB/s"
    assert _format_eta(None) == ""
    assert _format_eta(125) == "2:05"


def test_task_added_creates_a_row(qtbot):
    manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
    page = QueuePage(manager)
    qtbot.addWidget(page)

    task = _make_task(title="My Video")
    hold = {task.url: threading.Event()}
    hold[task.url].set()

    with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(hold)):
        manager.add_task(task)
        qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.COMPLETED, timeout=2000)

    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "My Video"
    assert page.table.item(0, 1).text() == "Completed"

    progress_bar = page.table.cellWidget(0, 2)
    assert isinstance(progress_bar, QProgressBar)
    assert progress_bar.value() == 100

    manager.shutdown()


def test_progress_updates_speed_and_eta_columns(qtbot):
    manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
    page = QueuePage(manager)
    qtbot.addWidget(page)

    task = _make_task()
    hold = {task.url: threading.Event()}

    with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(hold)):
        manager.add_task(task)
        qtbot.waitUntil(lambda: page.table.item(0, 3).text() != "", timeout=2000)

        assert "KB/s" in page.table.item(0, 3).text()
        assert page.table.item(0, 4).text() == "0:05"

        hold[task.url].set()
        qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.COMPLETED, timeout=2000)

    manager.shutdown()


def test_cancel_button_click_cancels_active_download(qtbot):
    manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
    page = QueuePage(manager)
    qtbot.addWidget(page)

    task = _make_task()

    def _factory(opts):
        mock_ydl = MagicMock()

        def _download(urls):
            hooks = opts.get("progress_hooks", [])
            for i in range(200):
                for hook in hooks:
                    hook({"status": "downloading", "downloaded_bytes": i, "total_bytes": 1000})
                threading.Event().wait(0.005)

        mock_ydl.download.side_effect = _download
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = False
        return mock_ydl

    with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_factory):
        manager.add_task(task)
        qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.DOWNLOADING, timeout=2000)

        container = page.table.cellWidget(0, 5)
        cancel_button = container.findChild(QPushButton, "cancel_button")
        cancel_button.click()

        qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.CANCELLED, timeout=2000)

    assert "Cancelled" in page.table.item(0, 1).text()
    manager.shutdown()


def test_remove_button_removes_row(qtbot):
    manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
    page = QueuePage(manager)
    qtbot.addWidget(page)

    task_a = _make_task("https://example.com/a")
    task_b = _make_task("https://example.com/b")
    hold = {task_a.url: threading.Event(), task_b.url: threading.Event()}

    with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(hold)):
        manager.add_task(task_a)
        manager.add_task(task_b)
        qtbot.waitUntil(lambda: manager.get_task(task_a.id).status == DownloadStatus.DOWNLOADING, timeout=2000)

        assert page.table.rowCount() == 2

        container = page.table.cellWidget(1, 5)  # task_b's row (still queued)
        remove_button = container.findChild(QPushButton, "remove_button")
        remove_button.click()

        assert page.table.rowCount() == 1

        hold[task_a.url].set()
        qtbot.waitUntil(lambda: manager.get_task(task_a.id).status == DownloadStatus.COMPLETED, timeout=2000)

    manager.shutdown()


def test_clear_completed_button_removes_completed_rows(qtbot):
    manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
    page = QueuePage(manager)
    qtbot.addWidget(page)

    task = _make_task()
    hold = {task.url: threading.Event()}
    hold[task.url].set()

    with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(hold)):
        manager.add_task(task)
        qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.COMPLETED, timeout=2000)

    assert page.table.rowCount() == 1
    page.clear_completed_button.click()
    assert page.table.rowCount() == 0

    manager.shutdown()


def test_retry_button_visible_after_failure(qtbot):
    manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
    page = QueuePage(manager)
    qtbot.addWidget(page)

    task = _make_task()

    def _factory(opts):
        mock_ydl = MagicMock()
        import yt_dlp

        mock_ydl.download.side_effect = yt_dlp.utils.DownloadError("Video unavailable")
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = False
        return mock_ydl

    with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_factory):
        manager.add_task(task)
        qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.FAILED, timeout=2000)

    container = page.table.cellWidget(0, 5)
    retry_button = container.findChild(QPushButton, "retry_button")
    cancel_button = container.findChild(QPushButton, "cancel_button")

    assert not retry_button.isHidden()
    assert cancel_button.isHidden()
    assert "Failed" in page.table.item(0, 1).text()

    manager.shutdown()
