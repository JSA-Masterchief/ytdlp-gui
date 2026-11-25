"""Tests for the interactive bits of the redesigned UI: auto-analyze on
paste, Enter-to-analyze, format presets, responsive grid, empty states."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtWidgets import QApplication, QLabel

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.models import FormatInfo, MediaInfo
from download.history import HistoryStore
from download.task import DownloadStatus, DownloadTask
from formats.selector import MODE_AUDIO_ONLY, MODE_VIDEO_AUDIO, FormatSelection
from services.metadata_service import MetadataService
from ui.pages.download_page import DownloadPage
from ui.pages.history_page import HistoryPage
from ui.pages.queue_page import QueuePage
from ui.widgets.common import ResponsiveGrid
from ui.widgets.format_selector_widget import FormatSelectorWidget

MEDIA = MediaInfo(
    id="abc", title="Clip", webpage_url="https://example.com/abc", extractor="generic", duration=60,
    formats=[FormatInfo(format_id="1", ext="mp4", resolution="1280x720", vcodec="avc1", acodec="none")],
)


def _page(qtbot, analyze_result=MEDIA):
    backend = MagicMock()
    backend.analyze.return_value = analyze_result
    service = MetadataService(backend=backend)
    page = DownloadPage(metadata_service=service, download_manager=MagicMock())
    qtbot.addWidget(page)
    return page, service, backend


# ------------------------------------------------------------- link box

def test_pasting_a_link_analyzes_automatically(qtbot):
    page, service, backend = _page(qtbot)
    mime = QMimeData()
    mime.setText("  https://example.com/abc  ")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.url_input.insertFromMimeData(mime)
    assert page.url_input.toPlainText() == "https://example.com/abc"
    backend.analyze.assert_called_once()
    assert page.download_button.isEnabled()


def test_pasting_non_link_text_does_not_analyze(qtbot):
    page, _service, backend = _page(qtbot)
    mime = QMimeData()
    mime.setText("hello there")
    page.url_input.insertFromMimeData(mime)
    backend.analyze.assert_not_called()


def test_enter_analyzes_and_shift_enter_adds_a_line(qtbot):
    page, service, backend = _page(qtbot)
    page.url_input.setPlainText("https://example.com/abc")
    page.url_input.moveCursor(page.url_input.textCursor().MoveOperation.End)

    qtbot.keyClick(page.url_input, Qt.Key_Return, Qt.ShiftModifier)
    assert page.url_input.document().blockCount() == 2
    backend.analyze.assert_not_called()

    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        qtbot.keyClick(page.url_input, Qt.Key_Return)
    backend.analyze.assert_called_once()


def test_link_box_grows_with_more_links_up_to_a_limit(qtbot):
    page, _s, _b = _page(qtbot)
    one_line = page.url_input.height()
    page.url_input.setPlainText("https://a.com\nhttps://b.com\nhttps://c.com")
    three_lines = page.url_input.height()
    page.url_input.setPlainText("\n".join(f"https://{i}.com" for i in range(10)))
    many_lines = page.url_input.height()
    assert one_line < three_lines < many_lines
    page.url_input.setPlainText("\n".join(f"https://{i}.com" for i in range(20)))
    assert page.url_input.height() == many_lines  # capped


def test_link_box_shows_placeholder(qtbot):
    page, _s, _b = _page(qtbot)
    assert "link" in page.url_input.placeholderText().lower()


def test_paste_button_uses_clipboard_and_analyzes(qtbot):
    page, service, backend = _page(qtbot)
    QApplication.clipboard().setText("https://example.com/abc")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.paste_button.click()
    assert page.url_input.toPlainText() == "https://example.com/abc"
    backend.analyze.assert_called_once()


def test_paste_button_with_empty_clipboard_explains(qtbot):
    page, _service, backend = _page(qtbot)
    QApplication.clipboard().setText("")
    page.paste_button.click()
    assert not page.status_label.isHidden()
    backend.analyze.assert_not_called()


def test_busy_state_while_analyzing(qtbot):
    page, service, _backend = _page(qtbot)
    with patch.object(service, "analyze"):
        page.url_input.setPlainText("https://example.com/abc")
        page.analyze_button.click()
        assert not page.busy_bar.isHidden()
        assert not page.analyze_button.isEnabled()
        assert not page.paste_button.isEnabled()
    page._on_analysis_finished("https://example.com/abc", MEDIA)
    assert page.busy_bar.isHidden()
    assert page.analyze_button.text() == "Analyze"


def test_queueing_offers_view_queue(qtbot):
    page, service, _backend = _page(qtbot)
    requested = []
    page.view_queue_requested.connect(lambda: requested.append(True))
    page.url_input.setPlainText("https://example.com/abc")
    with qtbot.waitSignal(service.analysis_finished, timeout=2000):
        page.analyze_button.click()
    with qtbot.waitSignal(page.task_queued, timeout=1000):
        page.download_button.click()
    assert not page.view_queue_button.isHidden()
    page.view_queue_button.click()
    assert requested


def test_change_folder_updates_output_and_emits(qtbot):
    page, _s, _b = _page(qtbot)
    with patch("ui.pages.download_page.QFileDialog.getExistingDirectory", return_value="D:/Media"):
        with qtbot.waitSignal(page.output_dir_changed, timeout=1000) as blocker:
            page.change_dir_button.click()
    assert blocker.args == ["D:/Media"]
    assert page._output_dir == "D:/Media"
    assert page.output_dir_label.toolTip() == "D:/Media"


def test_summary_describes_selection(qtbot):
    page, _s, _b = _page(qtbot)
    page.format_selector.apply_preset("mp3")
    assert "MP3" in page.summary_label.text()
    page.format_selector.apply_preset("720p")
    assert "720p" in page.summary_label.text()


# --------------------------------------------------------------- presets

def test_presets_set_the_dropdowns(qtbot):
    widget = FormatSelectorWidget()
    qtbot.addWidget(widget)
    widget.apply_preset("mp3")
    sel = widget.current_selection()
    assert sel.mode == MODE_AUDIO_ONLY and sel.audio_format == "mp3"
    assert widget.preset_buttons["mp3"].isChecked()

    widget.apply_preset("1080p")
    sel = widget.current_selection()
    assert sel.mode == MODE_VIDEO_AUDIO and sel.quality == "1080p"
    assert widget.preset_buttons["1080p"].isChecked()
    assert not widget.preset_buttons["mp3"].isChecked()


def test_manual_choice_highlights_matching_preset_or_none(qtbot):
    widget = FormatSelectorWidget()
    qtbot.addWidget(widget)
    widget.quality_combo.setCurrentIndex(widget.quality_combo.findData("480p"))
    assert not any(b.isChecked() for b in widget.preset_buttons.values())
    widget.quality_combo.setCurrentIndex(widget.quality_combo.findData("720p"))
    assert widget.preset_buttons["720p"].isChecked()


def test_unavailable_quality_presets_are_disabled(qtbot):
    widget = FormatSelectorWidget()
    qtbot.addWidget(widget)
    widget.set_available_heights([720, 480])
    assert widget.preset_buttons["720p"].isEnabled()
    assert not widget.preset_buttons["1080p"].isEnabled()
    assert widget.preset_buttons["best"].isEnabled()
    assert widget.preset_buttons["mp3"].isEnabled()


def test_audio_mode_swaps_visible_fields(qtbot):
    widget = FormatSelectorWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.apply_preset("mp3")
    assert widget.audio_field.isVisible() and not widget.container_field.isVisible()
    widget.apply_preset("best")
    assert widget.container_field.isVisible() and not widget.audio_field.isVisible()


def test_preset_emits_a_single_change(qtbot):
    widget = FormatSelectorWidget()
    qtbot.addWidget(widget)
    changes = []
    widget.selection_changed.connect(lambda: changes.append(1))
    widget.apply_preset("mp3")
    assert len(changes) == 1


# --------------------------------------------------------------- layout

def test_responsive_grid_reflows_columns(qtbot):
    grid = ResponsiveGrid(min_column_width=150, max_columns=4)
    qtbot.addWidget(grid)
    for i in range(4):
        grid.add_field(f"F{i}", QLabel("x"))
    grid.show()
    grid.resize(800, 100)
    qtbot.waitUntil(lambda: grid.columns() == 4, timeout=1000)
    grid.resize(400, 100)
    qtbot.waitUntil(lambda: grid.columns() == 2, timeout=1000)
    grid.resize(160, 100)
    qtbot.waitUntil(lambda: grid.columns() == 1, timeout=1000)


# ------------------------------------------------------------ empty states

def _task(title="Clip"):
    return DownloadTask(url="https://example.com/v", selection=FormatSelection(), output_dir="/tmp/dl",
                        filename_template="%(title)s.%(ext)s", ytdlp_options={}, title=title)


def test_queue_shows_empty_state_then_table(qtbot):
    manager = MagicMock()
    page = QueuePage(manager)
    qtbot.addWidget(page)
    assert page.stack.currentWidget() is page.empty_state
    page._on_task_added(_task())
    assert page.stack.currentWidget() is page.table
    assert "1 in progress" in page.summary_label.text()


def test_queue_reports_active_count_and_open_folder(qtbot):
    from PySide6.QtWidgets import QPushButton

    manager = MagicMock()
    page = QueuePage(manager)
    qtbot.addWidget(page)
    counts = []
    page.active_count_changed.connect(counts.append)
    task = _task()
    page._on_task_added(task)
    task.status = DownloadStatus.COMPLETED
    page._on_task_updated(task)
    assert counts[-1] == 0
    button = page.table.cellWidget(0, 5).findChild(QPushButton, "open_folder_button")
    assert not button.isHidden()
    with patch("ui.pages.queue_page.QDesktopServices.openUrl") as open_url:
        button.click()
    open_url.assert_called_once()


def test_queue_empty_state_button_requests_download_page(qtbot):
    page = QueuePage(MagicMock())
    qtbot.addWidget(page)
    with qtbot.waitSignal(page.browse_requested, timeout=1000):
        page.empty_state.action_button.click()


def test_history_empty_and_no_results_states(qtbot, tmp_path):
    from download.history import HistoryEntry

    store = HistoryStore(tmp_path / "history.json")
    page = HistoryPage(store)
    qtbot.addWidget(page)
    assert page.stack.currentWidget() is page.empty_state
    assert not page.clear_all_button.isEnabled()

    store.add(HistoryEntry.now(url="https://example.com/v", title="Cats", status="completed"))
    page.refresh()
    assert page.stack.currentWidget() is page.table
    page.search_edit.setText("dogs")
    assert page.stack.currentWidget() is page.no_results_state


def test_history_double_click_opens_file(qtbot, tmp_path):
    from download.history import HistoryEntry

    store = HistoryStore(tmp_path / "history.json")
    store.add(HistoryEntry.now(url="https://example.com/v", title="Cats", status="completed", file_path=str(tmp_path / "c.mp4")))
    page = HistoryPage(store)
    qtbot.addWidget(page)
    with patch("ui.pages.history_page.QDesktopServices.openUrl") as open_url:
        page.table.cellDoubleClicked.emit(0, 0)
    open_url.assert_called_once()
