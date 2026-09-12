from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from download.task import DownloadStatus, DownloadTask
from formats.selector import FormatSelection


def _make_task(**overrides) -> DownloadTask:
    defaults = dict(
        url="https://example.com/video",
        selection=FormatSelection(),
        output_dir="/tmp/downloads",
        filename_template="%(title)s.%(ext)s",
        ytdlp_options={"format": "best"},
    )
    defaults.update(overrides)
    return DownloadTask(**defaults)


def test_new_task_defaults_to_queued():
    task = _make_task()
    assert task.status == DownloadStatus.QUEUED
    assert not task.is_active
    assert not task.is_finished


def test_downloading_is_active_not_finished():
    task = _make_task(status=DownloadStatus.DOWNLOADING)
    assert task.is_active
    assert not task.is_finished


def test_completed_is_finished_not_active():
    task = _make_task(status=DownloadStatus.COMPLETED)
    assert task.is_finished
    assert not task.is_active


def test_can_retry_only_for_failed_cancelled_or_paused():
    for status in (DownloadStatus.FAILED, DownloadStatus.CANCELLED, DownloadStatus.PAUSED):
        assert _make_task(status=status).can_retry
    for status in (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING, DownloadStatus.COMPLETED):
        assert not _make_task(status=status).can_retry


def test_display_title_falls_back_to_url():
    task = _make_task(title=None)
    assert task.display_title == task.url

    task_with_title = _make_task(title="My Video")
    assert task_with_title.display_title == "My Video"


def test_ids_are_unique():
    first = _make_task()
    second = _make_task()
    assert first.id != second.id
