"""Tests for services.history_recorder.HistoryRecorder.

Uses a real DownloadManager + YtdlpBackend with only yt_dlp.YoutubeDL
mocked, so the recorder is exercised against genuine manager signal
traffic — same approach as test_download_manager.py.
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
from download.history import HistoryStore
from download.manager import DownloadManager
from download.task import DownloadStatus, DownloadTask
from formats.selector import FormatSelection
from services.history_recorder import HistoryRecorder


def _make_task(url: str = "https://example.com/v", title: str = "A Video") -> DownloadTask:
    return DownloadTask(
        url=url,
        selection=FormatSelection(quality="1080p"),
        output_dir="/tmp/downloads",
        filename_template="%(title)s.%(ext)s",
        ytdlp_options={"format": "best"},
        title=title,
    )


def _ydl_factory_success(hook_events):
    def _factory(opts):
        mock_ydl = MagicMock()

        def _download(urls):
            hooks = opts.get("progress_hooks", [])
            for event in hook_events:
                for hook in hooks:
                    hook(event)

        mock_ydl.download.side_effect = _download
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = False
        return mock_ydl

    return _factory


def test_completed_download_is_recorded(qtbot, tmp_path):
    manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
    store = HistoryStore(tmp_path / "history.json")
    recorder = HistoryRecorder(manager, store)  # noqa: F841 - must stay referenced, see module docstring

    task = _make_task(title="My Video")
    events = [{"status": "downloading", "downloaded_bytes": 1, "total_bytes": 1}, {"status": "finished", "filename": "/tmp/My Video.mp4"}]

    with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_ydl_factory_success(events)):
        manager.add_task(task)
        qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.COMPLETED, timeout=2000)

    entries = store.all_entries()
    assert len(entries) == 1
    assert entries[0].title == "My Video"
    assert entries[0].status == "completed"
    assert entries[0].file_path == "/tmp/My Video.mp4"
    assert entries[0].format_description == "1080p"

    manager.shutdown()


def test_failed_download_is_recorded_as_failed(qtbot, tmp_path):
    manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
    store = HistoryStore(tmp_path / "history.json")
    recorder = HistoryRecorder(manager, store)  # noqa: F841 - must stay referenced, see module docstring

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

    entries = store.all_entries()
    assert len(entries) == 1
    assert entries[0].status == "failed"

    manager.shutdown()


def test_cancelled_download_is_recorded_as_cancelled(qtbot, tmp_path):
    manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
    store = HistoryStore(tmp_path / "history.json")
    recorder = HistoryRecorder(manager, store)  # noqa: F841 - must stay referenced, see module docstring

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

    entries = store.all_entries()
    assert len(entries) == 1
    assert entries[0].status == "cancelled"

    manager.shutdown()


def test_recorder_is_a_qobject_so_it_survives_without_an_explicit_python_reference(tmp_path):
    """Regression test for a real lifetime bug: HistoryRecorder must be a
    QObject. A plain Python object connected to a signal can be garbage
    collected the moment the constructing scope ends if nothing else
    holds a reference, silently breaking history recording. Being a
    QObject at least makes `parent=` ownership possible and is part of
    the fix — this test documents why the class is a QObject at all.
    """
    from PySide6.QtCore import QObject

    manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
    store = HistoryStore(tmp_path / "history.json")
    recorder = HistoryRecorder(manager, store)

    assert isinstance(recorder, QObject)
    manager.shutdown()


def test_progress_updates_do_not_create_duplicate_entries(qtbot, tmp_path):
    """A task fires many task_updated signals while downloading (one per
    progress event) before it finishes — the recorder must only write
    history once, not once per progress tick.
    """
    manager = DownloadManager(backend=YtdlpBackend(), max_concurrent=1)
    store = HistoryStore(tmp_path / "history.json")
    recorder = HistoryRecorder(manager, store)  # noqa: F841 - must stay referenced, see module docstring

    task = _make_task()
    events = [{"status": "downloading", "downloaded_bytes": i, "total_bytes": 10} for i in range(1, 11)]
    events.append({"status": "finished", "filename": "/tmp/x.mp4"})

    with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_ydl_factory_success(events)):
        manager.add_task(task)
        qtbot.waitUntil(lambda: manager.get_task(task.id).status == DownloadStatus.COMPLETED, timeout=2000)

    assert len(store.all_entries()) == 1

    manager.shutdown()
