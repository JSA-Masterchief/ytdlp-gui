from __future__ import annotations
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
from backend.ytdlp_backend import YtdlpBackend
from download.manager import DownloadManager
from download.task import DownloadStatus, DownloadTask
from formats.selector import FormatSelection

def _make_task(url: str = "https://example.com/v") -> DownloadTask:
    return DownloadTask(url=url, selection=FormatSelection(), output_dir="/tmp/downloads", filename_template="%(title)s.%(ext)s", ytdlp_options={"format": "best"})

def _controllable_ydl_factory(release_events, hold_events):
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
        hold[task.url].set()
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


# --- remove() on an active task, and shutdown() edge cases -------------------

import time  # noqa: E402


def _looping_ydl_factory():
    """A download that reports progress constantly, so cancellation is prompt."""

    def _factory(opts):
        mock_ydl = MagicMock()

        def _download(urls):
            hooks = opts.get("progress_hooks", [])
            for i in range(1000):
                for hook in hooks:
                    hook({"status": "downloading", "downloaded_bytes": i, "total_bytes": 1000})
                threading.Event().wait(0.005)

        mock_ydl.download.side_effect = _download
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = False
        return mock_ydl

    return _factory


def _stalling_ydl_factory(release: threading.Event, stalled: list[str] | None = None):
    """A download that reports once, then blocks with NO further progress
    hooks until `release` is set — like an FFmpeg merge or a stalled socket,
    where yt-dlp has no chance to notice a cancellation request.

    `stalled` gets the URL appended at the moment the download is actually
    blocked. Tests must wait on it: DownloadStatus.DOWNLOADING is set
    synchronously by add_task, *before* the worker thread has started, so
    waiting on status alone races with shutdown() cancelling the download
    before it ever reaches the stall.
    """

    def _factory(opts):
        mock_ydl = MagicMock()

        def _download(urls):
            hooks = opts.get("progress_hooks", [])
            for hook in hooks:
                hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 100})
            if stalled is not None:
                stalled.append(urls[0])
            release.wait(timeout=10)

        mock_ydl.download.side_effect = _download
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = False
        return mock_ydl

    return _factory


class TestRemoveActiveTask:
    def test_removing_an_active_download_cancels_then_actually_removes_it(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task = _make_task()
        removed = []
        manager.task_removed.connect(removed.append)

        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_looping_ydl_factory()):
            manager.add_task(task)
            qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.DOWNLOADING, timeout=2000)

            manager.remove(task.id)
            qtbot.waitUntil(lambda: manager.get_task(task.id) is None, timeout=3000)

        assert removed == [task.id]
        assert task.id not in [t.id for t in manager.all_tasks()]
        manager.shutdown()

    def test_removing_an_active_task_still_lets_the_next_queued_task_start(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task_a = _make_task("https://example.com/a")
        task_b = _make_task("https://example.com/b")
        hold = {task_b.url: threading.Event()}
        release = {task_b.url: threading.Event()}

        def _factory(opts):
            # a loops (cancellable); b completes promptly
            def _download(urls):
                hooks = opts.get("progress_hooks", [])
                if urls[0] == task_a.url:
                    for i in range(1000):
                        for hook in hooks:
                            hook({"status": "downloading", "downloaded_bytes": i, "total_bytes": 1000})
                        threading.Event().wait(0.005)
                else:
                    for hook in hooks:
                        hook({"status": "finished", "filename": "b.mp4"})

            mock_ydl = MagicMock()
            mock_ydl.download.side_effect = _download
            mock_ydl.__enter__.return_value = mock_ydl
            mock_ydl.__exit__.return_value = False
            return mock_ydl

        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_factory):
            manager.add_task(task_a)
            manager.add_task(task_b)
            qtbot.waitUntil(lambda: manager.get_task(task_a.id).status == DownloadStatus.DOWNLOADING, timeout=2000)

            manager.remove(task_a.id)
            qtbot.waitUntil(lambda: manager.get_task(task_a.id) is None, timeout=3000)
            qtbot.waitUntil(lambda: manager.get_task(task_b.id).status == DownloadStatus.COMPLETED, timeout=3000)

        manager.shutdown()

    def test_removing_a_finished_task_is_immediate(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task = _make_task()
        hold = {task.url: threading.Event()}
        release = {task.url: threading.Event()}
        hold[task.url].set()
        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_controllable_ydl_factory(release, hold)):
            manager.add_task(task)
            qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.COMPLETED, timeout=2000)

        manager.remove(task.id)
        assert manager.get_task(task.id) is None
        manager.shutdown()


class TestShutdown:
    def test_shutdown_with_nothing_active_returns_immediately(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        start = time.monotonic()
        manager.shutdown()
        assert time.monotonic() - start < 0.5
        assert not manager.has_orphaned_threads

    def test_shutdown_is_idempotent(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        manager.shutdown()
        manager.shutdown()

    def test_shutdown_stops_a_promptly_cancellable_download_without_orphans(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task = _make_task()
        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_looping_ydl_factory()):
            manager.add_task(task)
            qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.DOWNLOADING, timeout=2000)

            start = time.monotonic()
            manager.shutdown(timeout_ms=3000)
            elapsed = time.monotonic() - start

        assert elapsed < 1.5
        assert not manager.has_orphaned_threads
        assert manager.active_count == 0

    def test_shutdown_does_not_block_on_a_stalled_download(self, qtbot):
        """Regression test: shutdown() used to wait for a download that
        reports no progress for as long as it stayed stalled (an FFmpeg
        merge can take minutes), freezing the window on close.
        """
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task = _make_task()
        release = threading.Event()
        stalled: list[str] = []
        try:
            with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_stalling_ydl_factory(release, stalled)):
                manager.add_task(task)
                qtbot.waitUntil(lambda: len(stalled) == 1, timeout=3000)

                start = time.monotonic()
                manager.shutdown(timeout_ms=200)
                elapsed = time.monotonic() - start

                assert elapsed < 2.0, f"shutdown blocked for {elapsed:.1f}s on a stalled download"
                assert manager.has_orphaned_threads
        finally:
            release.set()
            qtbot.waitUntil(lambda: not manager.has_orphaned_threads, timeout=5000)

    def test_shutdown_timeout_is_one_shared_budget_not_per_download(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=2)
        task_a = _make_task("https://example.com/a")
        task_b = _make_task("https://example.com/b")
        release = threading.Event()
        stalled: list[str] = []
        try:
            with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_stalling_ydl_factory(release, stalled)):
                manager.add_task(task_a)
                manager.add_task(task_b)
                qtbot.waitUntil(lambda: len(stalled) == 2, timeout=3000)

                start = time.monotonic()
                manager.shutdown(timeout_ms=500)
                elapsed = time.monotonic() - start

                # Per-download budgets would take ~1.0s; one shared budget ~0.5s.
                assert elapsed < 0.9, f"took {elapsed:.2f}s - timeout looks per-download, not shared"
        finally:
            release.set()
            qtbot.waitUntil(lambda: not manager.has_orphaned_threads, timeout=5000)

    def test_shutdown_never_starts_queued_downloads(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task_a = _make_task("https://example.com/a")
        task_b = _make_task("https://example.com/b")
        release = threading.Event()
        started: list[str] = []
        try:
            with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_stalling_ydl_factory(release, started)):
                manager.add_task(task_a)
                manager.add_task(task_b)
                qtbot.waitUntil(lambda: len(started) == 1, timeout=3000)

                manager.shutdown(timeout_ms=100)

                # Let the orphaned download finish; its late "finished" event
                # would previously free a slot and start task_b mid-shutdown.
                release.set()
                qtbot.waitUntil(lambda: not manager.has_orphaned_threads, timeout=5000)
                qtbot.wait(300)
        finally:
            release.set()

        assert started == [task_a.url]
        assert manager.get_task(task_b.id).status == DownloadStatus.QUEUED

    def test_late_events_from_an_orphaned_download_are_ignored(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task = _make_task()
        release = threading.Event()
        stalled: list[str] = []
        updates = []
        try:
            with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_stalling_ydl_factory(release, stalled)):
                manager.add_task(task)
                qtbot.waitUntil(lambda: len(stalled) == 1, timeout=3000)

                manager.shutdown(timeout_ms=100)
                manager.task_updated.connect(updates.append)

                release.set()
                qtbot.waitUntil(lambda: not manager.has_orphaned_threads, timeout=5000)
                qtbot.wait(300)
        finally:
            release.set()

        assert updates == []  # nothing resurrected the task after shutdown


class TestMaxConcurrentChanges:
    def test_raising_the_limit_starts_queued_downloads_immediately(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
        task_a = _make_task("https://example.com/a")
        task_b = _make_task("https://example.com/b")
        release = threading.Event()
        stalled: list[str] = []
        try:
            with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_stalling_ydl_factory(release, stalled)):
                manager.add_task(task_a)
                manager.add_task(task_b)
                qtbot.waitUntil(lambda: len(stalled) == 1, timeout=3000)
                assert manager.get_task(task_b.id).status == DownloadStatus.QUEUED

                manager.set_max_concurrent(2)

                qtbot.waitUntil(lambda: len(stalled) == 2, timeout=3000)
                assert manager.max_concurrent == 2
                assert manager.active_count == 2
        finally:
            release.set()
            qtbot.waitUntil(
                lambda: all(manager.get_task(t.id).status == DownloadStatus.COMPLETED for t in (task_a, task_b)),
                timeout=5000,
            )
            manager.shutdown()

    @pytest.mark.parametrize("requested", [0, -5])
    def test_limit_below_one_is_clamped_to_one(self, qtbot, requested):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=3)
        manager.set_max_concurrent(requested)
        assert manager.max_concurrent == 1
        manager.shutdown()

    def test_constructor_clamps_a_nonsense_limit(self, qtbot):
        manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=0)
        assert manager.max_concurrent == 1
        manager.shutdown()
