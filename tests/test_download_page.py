"""Integration test covering DownloadPage's Analyze -> MetadataPanel ->
FormatSelectorWidget wiring, with a mocked backend (no real network calls).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.models import FormatInfo, MediaInfo
from services.metadata_service import MetadataService
from ui.pages.download_page import DownloadPage

SAMPLE_MEDIA = MediaInfo(
    id="abc123",
    title="Sample Video",
    webpage_url="https://example.com/abc123",
    extractor="generic",
    duration=90,
    formats=[
        FormatInfo(format_id="1", ext="mp4", resolution="1920x1080", vcodec="avc1", acodec="none"),
        FormatInfo(format_id="2", ext="mp4", resolution="1280x720", vcodec="avc1", acodec="none"),
        FormatInfo(format_id="3", ext="m4a", vcodec="none", acodec="mp4a"),
    ],
)


def test_analyze_click_populates_metadata_and_restricts_quality(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_MEDIA
    service = MetadataService(backend=backend)

    page = DownloadPage(metadata_service=service)
    qtbot.addWidget(page)

    page.url_input.setPlainText("https://example.com/abc123")

    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()

    assert page.metadata_panel.title_label.text() == "Sample Video"

    quality_values = [page.format_selector.quality_combo.itemData(i) for i in range(page.format_selector.quality_combo.count())]
    assert "1080p" in quality_values
    assert "720p" in quality_values
    assert "480p" not in quality_values

    assert page.analyze_button.isEnabled()
    assert page.analyze_button.text() == "Analyze"


def test_invalid_url_shows_status_and_does_not_call_backend(qtbot):
    backend = MagicMock()
    service = MetadataService(backend=backend)
    page = DownloadPage(metadata_service=service)
    qtbot.addWidget(page)

    page.url_input.setPlainText("not a url at all")
    page.analyze_button.click()

    assert not page.status_label.isHidden()
    backend.analyze.assert_not_called()


def test_preview_updates_when_url_typed(qtbot):
    backend = MagicMock()
    service = MetadataService(backend=backend)
    page = DownloadPage(metadata_service=service)
    qtbot.addWidget(page)

    page.url_input.setPlainText("https://example.com/xyz")

    assert "example.com/xyz" in page.format_selector.preview_box.toPlainText()


def test_download_button_disabled_until_analysis_completes(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_MEDIA
    service = MetadataService(backend=backend)
    manager = MagicMock()

    page = DownloadPage(metadata_service=service, download_manager=manager)
    qtbot.addWidget(page)

    assert not page.download_button.isEnabled()

    page.url_input.setPlainText("https://example.com/abc123")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()

    assert page.download_button.isEnabled()


def test_download_button_adds_task_to_manager(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_MEDIA
    service = MetadataService(backend=backend)
    manager = MagicMock()

    page = DownloadPage(metadata_service=service, download_manager=manager)
    qtbot.addWidget(page)

    page.url_input.setPlainText("https://example.com/abc123")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()

    page.download_button.click()

    manager.add_task.assert_called_once()
    added_task = manager.add_task.call_args[0][0]
    assert added_task.url == "https://example.com/abc123"
    assert added_task.title == "Sample Video"
    assert not page.queued_label.isHidden()
