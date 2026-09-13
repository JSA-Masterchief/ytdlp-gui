"""Tests for download.manager.DownloadManager.

Uses the real YtdlpBackend with a controllable fake YoutubeDL so downloads
can be paused mid-flight from the test, letting us deterministically
exercise concurrency limits and cancellation without real timing races.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.ytdlp_backend import YtdlpBackend
from download.manager import DownloadManager
from download.task import DownloadStatus, DownloadTask
from formats.selector import FormatSelection


def _make_task(url: str = "https://example.com/v") -> DownloadTask:
    return DownloadTask(
        url=url,
        selection=FormatSelection(),
        output_dir="/tmp/downloads",
        filename_template="%(title)s.%(ext)s",
        ytdlp_options={"format": "best"},
    )


def _controllable_ydl_factory(release_events: dict[str, threading.Event], hold_events: dict[str, threading.Event]):
    """Each download blocks on its own hold_event (keyed by url) until the
    test sets it, letting tests control exactly when a "download" finishes.
    """

    def _factory(opts):
        mock_ydl = MagicMock()

        def _download(urls):
            url = urls[0]
            hooks = opts.get("progress_hooks", [])
            for hook in hooks:
                hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 100})
            hold_events[url].wait(timeout=5)
            for hook in hooks:
                hook({"status": "finished", "filename": f"{url}.mp4"})
            release_events[url].set()

        mock_ydl.download.side_effect = _download
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = False
        return mock_ydl

    return _factory


class TestBasicFlow:
    def test_add_task_starts_immediately_when_slot_free(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=2)
        task = _make_task()

        added = []
        manager.task_added.connect(lambda t: added.append(t))

        hold = {task.url: threading.Event()}
        release = {task.url: threading.Event()}
        hold[task.url].set()  # let it finish immediately

        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(release, hold)):
            manager.add_task(task)
            qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.COMPLETED, timeout=2000)

        assert added == [task]
        manager.shutdown()

    def test_failed_download_marks_task_failed_with_message(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task = _make_task()

        def _factory(opts):
            mock_ydl = MagicMock()
            import yt_dlp

            mock_ydl.download.side_effect = yt_dlp.utils.DownloadError("Private video")
            mock_ydl.__enter__.return_value = mock_ydl
            mock_ydl.__exit__.return_value = False
            return mock_ydl

        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_factory):
            manager.add_task(task)
            qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.FAILED, timeout=2000)

        assert manager.get_task(task.id).error_message is not None
        manager.shutdown()


class TestConcurrencyLimit:
    def test_second_task_waits_when_max_concurrent_is_one(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task_a = _make_task("https://example.com/a")
        task_b = _make_task("https://example.com/b")

        hold = {task_a.url: threading.Event(), task_b.url: threading.Event()}
        release = {task_a.url: threading.Event(), task_b.url: threading.Event()}

        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(release, hold)):
            manager.add_task(task_a)
            manager.add_task(task_b)

            qtbot.waitUntil(lambda: manager.get_task(task_a.id).status == DownloadStatus.DOWNLOADING, timeout=2000)
            assert manager.get_task(task_b.id).status == DownloadStatus.QUEUED
            assert manager.active_count == 1

            hold[task_a.url].set()
            qtbot.waitUntil(lambda: manager.get_task(task_a.id).status == DownloadStatus.COMPLETED, timeout=2000)
            qtbot.waitUntil(lambda: manager.get_task(task_b.id).status == DownloadStatus.DOWNLOADING, timeout=2000)

            hold[task_b.url].set()
            qtbot.waitUntil(lambda: manager.get_task(task_b.id).status == DownloadStatus.COMPLETED, timeout=2000)

        manager.shutdown()


class TestCancelAndRetry:
    def test_cancel_active_download_marks_cancelled(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
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

            manager.cancel(task.id)
            qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.CANCELLED, timeout=2000)

        manager.shutdown()

    def test_cancel_queued_task_removes_it_from_pending(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task_a = _make_task("https://example.com/a")
        task_b = _make_task("https://example.com/b")

        hold = {task_a.url: threading.Event(), task_b.url: threading.Event()}
        release = {task_a.url: threading.Event(), task_b.url: threading.Event()}

        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(release, hold)):
            manager.add_task(task_a)
            manager.add_task(task_b)
            qtbot.waitUntil(lambda: manager.get_task(task_a.id).status == DownloadStatus.DOWNLOADING, timeout=2000)

            manager.cancel(task_b.id)
            assert manager.get_task(task_b.id).status == DownloadStatus.CANCELLED

            hold[task_a.url].set()
            qtbot.waitUntil(lambda: manager.get_task(task_a.id).status == DownloadStatus.COMPLETED, timeout=2000)

        manager.shutdown()

    def test_retry_requeues_a_failed_task(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task = _make_task()

        def _failing_factory(opts):
            mock_ydl = MagicMock()
            import yt_dlp

            mock_ydl.download.side_effect = yt_dlp.utils.DownloadError("Network issue")
            mock_ydl.__enter__.return_value = mock_ydl
            mock_ydl.__exit__.return_value = False
            return mock_ydl

        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_failing_factory):
            manager.add_task(task)
            qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.FAILED, timeout=2000)

        hold = {task.url: threading.Event()}
        release = {task.url: threading.Event()}
        hold[task.url].set()

        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(release, hold)):
            manager.retry(task.id)
            qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.COMPLETED, timeout=2000)

        assert manager.get_task(task.id).error_message is None
        manager.shutdown()


class TestQueueManagement:
    def test_remove_queued_task(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task_a = _make_task("https://example.com/a")
        task_b = _make_task("https://example.com/b")

        hold = {task_a.url: threading.Event(), task_b.url: threading.Event()}
        release = {task_a.url: threading.Event(), task_b.url: threading.Event()}

        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(release, hold)):
            manager.add_task(task_a)
            manager.add_task(task_b)
            qtbot.waitUntil(lambda: manager.get_task(task_a.id).status == DownloadStatus.DOWNLOADING, timeout=2000)

            manager.remove(task_b.id)
            assert manager.get_task(task_b.id) is None
            assert task_b.id not in [t.id for t in manager.all_tasks()]

            hold[task_a.url].set()
            qtbot.waitUntil(lambda: manager.get_task(task_a.id).status == DownloadStatus.COMPLETED, timeout=2000)

        manager.shutdown()

    def test_reorder_only_affects_pending_tasks(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task_a = _make_task("https://example.com/a")
        task_b = _make_task("https://example.com/b")
        task_c = _make_task("https://example.com/c")

        hold = {t.url: threading.Event() for t in (task_a, task_b, task_c)}
        release = {t.url: threading.Event() for t in (task_a, task_b, task_c)}

        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(release, hold)):
            manager.add_task(task_a)
            manager.add_task(task_b)
            manager.add_task(task_c)
            qtbot.waitUntil(lambda: manager.get_task(task_a.id).status == DownloadStatus.DOWNLOADING, timeout=2000)

            manager.move_up(task_c.id)
            assert manager._pending == [task_c.id, task_b.id]

            hold[task_a.url].set()
            qtbot.waitUntil(lambda: manager.get_task(task_c.id).status == DownloadStatus.DOWNLOADING, timeout=2000)

            hold[task_c.url].set()
            hold[task_b.url].set()
            qtbot.waitUntil(lambda: manager.get_task(task_b.id).status == DownloadStatus.COMPLETED, timeout=3000)

        manager.shutdown()

    def test_clear_completed_removes_only_completed_tasks(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task = _make_task()

        hold = {task.url: threading.Event()}
        release = {task.url: threading.Event()}
        hold[task.url].set()

        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(release, hold)):
            manager.add_task(task)
            qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.COMPLETED, timeout=2000)

        manager.clear_completed()
        assert manager.get_task(task.id) is None
        manager.shutdown()
