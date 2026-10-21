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

SAMPLE_MEDIA = MediaInfo(id="abc123", title="Test Video", webpage_url="https://example.com/abc123", extractor="generic")

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
    received = []
    service.analysis_finished.connect(lambda url, result: received.append((url, result)))
    service.analyze("https://example.com/abc123")
    assert backend.analyze.call_count == 1
    assert received == [("https://example.com/abc123", SAMPLE_MEDIA)]


# --- unexpected errors, the in-flight guard, and cache controls ---------------

import threading  # noqa: E402


def test_unexpected_backend_exception_becomes_a_generic_failure(qtbot):
    backend = MagicMock()
    backend.analyze.side_effect = ValueError("boom")
    service = MetadataService(backend=backend)

    with qtbot.waitSignal(service.analysis_failed, timeout=2000) as blocker:
        service.analyze("https://example.com/1")

    url, user_message, technical_detail = blocker.args
    assert url == "https://example.com/1"
    assert user_message == "An unexpected error occurred."
    assert "boom" in technical_detail


def test_a_second_request_while_one_is_running_is_ignored(qtbot):
    release = threading.Event()
    calls: list[str] = []

    def slow_analyze(url):
        calls.append(url)
        release.wait(timeout=5)
        return SAMPLE_MEDIA

    backend = MagicMock()
    backend.analyze.side_effect = slow_analyze
    service = MetadataService(backend=backend)

    try:
        service.analyze("https://example.com/1")
        qtbot.waitUntil(lambda: len(calls) == 1, timeout=2000)

        service.analyze("https://example.com/2")  # must not start a second thread
        qtbot.wait(150)

        assert calls == ["https://example.com/1"]
    finally:
        with qtbot.waitSignal(service.analysis_finished, timeout=5000):
            release.set()


def test_clear_cache_forces_a_fresh_backend_call(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_MEDIA
    service = MetadataService(backend=backend)

    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        service.analyze("https://example.com/1")
    service.clear_cache()
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        service.analyze("https://example.com/1")

    assert backend.analyze.call_count == 2


def test_use_cache_false_bypasses_a_cached_result(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_MEDIA
    service = MetadataService(backend=backend)

    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        service.analyze("https://example.com/1")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        service.analyze("https://example.com/1", use_cache=False)

    assert backend.analyze.call_count == 2


def test_failed_analysis_is_not_cached(qtbot):
    backend = MagicMock()
    backend.analyze.side_effect = [YtdlpBackendError("Network connection failed.", "x"), SAMPLE_MEDIA]
    service = MetadataService(backend=backend)

    with qtbot.waitSignal(service.analysis_failed, timeout=2000):
        service.analyze("https://example.com/1")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        service.analyze("https://example.com/1")  # retry must reach the backend again

    assert backend.analyze.call_count == 2
