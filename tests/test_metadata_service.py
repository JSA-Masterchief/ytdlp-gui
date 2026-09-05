"""Tests for services.metadata_service.MetadataService.

Uses pytest-qt's qtbot to run the real QThread event loop (not mocking Qt
itself) but mocks YtdlpBackend so no network calls happen.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.models import MediaInfo
from backend.ytdlp_backend import YtdlpBackendError
from services.metadata_service import MetadataService

SAMPLE_MEDIA = MediaInfo(
    id="abc123",
    title="Test Video",
    webpage_url="https://example.com/abc123",
    extractor="generic",
)


def test_analyze_emits_finished_with_result(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_MEDIA
    service = MetadataService(backend=backend)

    with qtbot.waitSignal(service.analysis_finished, timeout=2000) as blocker:
        service.analyze("https://example.com/abc123")

    url, result = blocker.args
    assert url == "https://example.com/abc123"
    assert result is SAMPLE_MEDIA
    backend.analyze.assert_called_once_with("https://example.com/abc123")


def test_analyze_emits_failed_on_backend_error(qtbot):
    backend = MagicMock()
    backend.analyze.side_effect = YtdlpBackendError("Video unavailable.", "raw detail")
    service = MetadataService(backend=backend)

    with qtbot.waitSignal(service.analysis_failed, timeout=2000) as blocker:
        service.analyze("https://example.com/missing")

    url, user_message, technical_detail = blocker.args
    assert url == "https://example.com/missing"
    assert user_message == "Video unavailable."
    assert technical_detail == "raw detail"


def test_second_analyze_uses_cache_without_calling_backend_again(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_MEDIA
    service = MetadataService(backend=backend)

    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        service.analyze("https://example.com/abc123")

    # Second call for the same URL should hit the cache synchronously.
    received = []
    service.analysis_finished.connect(lambda url, result: received.append((url, result)))
    service.analyze("https://example.com/abc123")

    assert backend.analyze.call_count == 1
    assert received == [("https://example.com/abc123", SAMPLE_MEDIA)]
