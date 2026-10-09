from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import MagicMock
SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
from backend.models import FormatInfo, MediaInfo, PlaylistEntry, PlaylistInfo
from services.metadata_service import MetadataService
from ui.pages.download_page import DownloadPage

SAMPLE_MEDIA = MediaInfo(
    id="abc123", title="Sample Video", webpage_url="https://example.com/abc123", extractor="generic", duration=90,
    formats=[
        FormatInfo(format_id="1", ext="mp4", resolution="1920x1080", vcodec="avc1", acodec="none"),
        FormatInfo(format_id="2", ext="mp4", resolution="1280x720", vcodec="avc1", acodec="none"),
        FormatInfo(format_id="3", ext="m4a", vcodec="none", acodec="mp4a"),
    ],
)

SAMPLE_PLAYLIST = PlaylistInfo(
    id="pl1", title="Sample Playlist", uploader="Someone", webpage_url="https://example.com/playlist",
    entries=[
        PlaylistEntry(id="v1", title="Video 1", url="https://example.com/v1", duration=60, index=1),
        PlaylistEntry(id="v2", title="Video 2", url="https://example.com/v2", duration=90, index=2),
        PlaylistEntry(id="v3", title="Video 3", url="https://example.com/v3", duration=120, index=3),
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

def test_analyzing_playlist_shows_playlist_table_and_hides_it_for_video(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_PLAYLIST
    service = MetadataService(backend=backend)
    manager = MagicMock()
    page = DownloadPage(metadata_service=service, download_manager=manager)
    qtbot.addWidget(page)
    assert page.playlist_table.isHidden()
    page.url_input.setPlainText("https://example.com/playlist")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()
    assert not page.playlist_table.isHidden()
    assert page.playlist_table.table.rowCount() == 3
    assert page.download_button.isEnabled()

def test_download_click_on_playlist_enqueues_one_task_per_entry(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_PLAYLIST
    service = MetadataService(backend=backend)
    manager = MagicMock()
    page = DownloadPage(metadata_service=service, download_manager=manager)
    qtbot.addWidget(page)
    page.url_input.setPlainText("https://example.com/playlist")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()
    page.download_button.click()
    assert manager.add_task.call_count == 3
    urls = [call.args[0].url for call in manager.add_task.call_args_list]
    assert urls == ["https://example.com/v1", "https://example.com/v2", "https://example.com/v3"]
    assert "3 video(s)" in page.queued_label.text()

def test_download_click_on_playlist_respects_selected_mode(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_PLAYLIST
    service = MetadataService(backend=backend)
    manager = MagicMock()
    page = DownloadPage(metadata_service=service, download_manager=manager)
    qtbot.addWidget(page)
    page.url_input.setPlainText("https://example.com/playlist")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()
    page.playlist_table.mode_selected_radio.setChecked(True)
    page.playlist_table._checkboxes[2].setChecked(False)
    page.download_button.click()
    urls = [call.args[0].url for call in manager.add_task.call_args_list]
    assert urls == ["https://example.com/v1", "https://example.com/v3"]

def test_download_click_on_playlist_with_no_selection_does_not_enqueue(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_PLAYLIST
    service = MetadataService(backend=backend)
    manager = MagicMock()
    page = DownloadPage(metadata_service=service, download_manager=manager)
    qtbot.addWidget(page)
    page.url_input.setPlainText("https://example.com/playlist")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()
    page.playlist_table.mode_selected_radio.setChecked(True)
    page.playlist_table.select_none_button.click()
    page.download_button.click()
    manager.add_task.assert_not_called()
    assert "No videos selected" in page.queued_label.text()

def test_analyzing_single_video_after_playlist_hides_playlist_table_again(qtbot):
    backend = MagicMock()
    backend.analyze.side_effect = [SAMPLE_PLAYLIST, SAMPLE_MEDIA]
    service = MetadataService(backend=backend)
    manager = MagicMock()
    page = DownloadPage(metadata_service=service, download_manager=manager)
    qtbot.addWidget(page)
    page.url_input.setPlainText("https://example.com/playlist")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()
    assert not page.playlist_table.isHidden()
    page.url_input.setPlainText("https://example.com/single-video")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()
    assert page.playlist_table.isHidden()

def test_custom_args_reflected_in_command_preview(qtbot):
    backend = MagicMock()
    service = MetadataService(backend=backend)
    page = DownloadPage(metadata_service=service, download_manager=MagicMock())
    qtbot.addWidget(page)
    page.custom_args.args_edit.setText("--limit-rate 500K")
    assert "--limit-rate 500K" in page.format_selector.preview_box.toPlainText()

def test_custom_args_conflict_with_format_is_shown_and_wins(qtbot):
    backend = MagicMock()
    service = MetadataService(backend=backend)
    page = DownloadPage(metadata_service=service, download_manager=MagicMock())
    qtbot.addWidget(page)
    page.custom_args.args_edit.setText("-f worst")
    assert not page.custom_args.conflict_label.isHidden()
    assert "format" in page.custom_args.conflict_label.text()

def test_download_blocked_while_custom_args_invalid(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_MEDIA
    service = MetadataService(backend=backend)
    manager = MagicMock()
    page = DownloadPage(metadata_service=service, download_manager=manager)
    qtbot.addWidget(page)
    page.url_input.setPlainText("https://example.com/abc123")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()
    page.custom_args.args_edit.setText("--this-is-not-a-real-flag")
    page.download_button.click()
    manager.add_task.assert_not_called()
    assert "custom arguments" in page.queued_label.text().lower()

def test_valid_custom_args_are_merged_into_enqueued_task(qtbot):
    backend = MagicMock()
    backend.analyze.return_value = SAMPLE_MEDIA
    service = MetadataService(backend=backend)
    manager = MagicMock()
    page = DownloadPage(metadata_service=service, download_manager=manager)
    qtbot.addWidget(page)
    page.url_input.setPlainText("https://example.com/abc123")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()
    page.custom_args.args_edit.setText("--limit-rate 500K")
    page.download_button.click()
    manager.add_task.assert_called_once()
    added_task = manager.add_task.call_args[0][0]
    assert added_task.ytdlp_options.get("ratelimit") == 512000


def test_apply_settings_updates_output_dir_and_preview(qtbot):
    backend = MagicMock()
    service = MetadataService(backend=backend)
    page = DownloadPage(metadata_service=service, download_manager=MagicMock())
    qtbot.addWidget(page)

    page.apply_settings("/new/download/dir", "%(id)s.%(ext)s")

    assert page._output_dir == "/new/download/dir"
    assert page._filename_template == "%(id)s.%(ext)s"
    assert "/new/download/dir" in page.format_selector.preview_box.toPlainText()


def test_set_url_populates_url_input(qtbot):
    backend = MagicMock()
    service = MetadataService(backend=backend)
    page = DownloadPage(metadata_service=service, download_manager=MagicMock())
    qtbot.addWidget(page)

    page.set_url("https://example.com/redownload-me")

    assert page.url_input.toPlainText() == "https://example.com/redownload-me"


def test_initial_output_dir_and_template_are_used(qtbot):
    backend = MagicMock()
    service = MetadataService(backend=backend)
    page = DownloadPage(
        metadata_service=service,
        download_manager=MagicMock(),
        initial_output_dir="/configured/dir",
        initial_filename_template="%(uploader)s.%(ext)s",
    )
    qtbot.addWidget(page)

    assert page._output_dir == "/configured/dir"
    assert page._filename_template == "%(uploader)s.%(ext)s"
