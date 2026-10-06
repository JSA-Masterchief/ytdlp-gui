from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QPushButton

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from download.history import HistoryEntry, HistoryStore
from ui.pages.history_page import HistoryPage, _format_timestamp


def _entry(**overrides) -> HistoryEntry:
    defaults = dict(url="https://example.com/v", title="Video", status="completed")
    defaults.update(overrides)
    return HistoryEntry.now(**defaults)


def test_format_timestamp_truncates_to_minute():
    assert _format_timestamp("2024-03-15T14:30:45.123456+00:00") == "2024-03-15 14:30"


def test_loads_entries_on_construction(qtbot, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    store.add(_entry(title="My Video"))

    page = HistoryPage(store)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "My Video"


def test_search_filters_rows(qtbot, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    store.add(_entry(title="Learn Python"))
    store.add(_entry(title="Cooking Pasta"))

    page = HistoryPage(store)
    qtbot.addWidget(page)
    assert page.table.rowCount() == 2

    page.search_edit.setText("python")
    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "Learn Python"


def test_remove_button_deletes_entry(qtbot, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    entry = _entry(title="Removable")
    store.add(entry)

    page = HistoryPage(store)
    qtbot.addWidget(page)

    container = page.table.cellWidget(0, 4)
    remove_button = container.findChild(QPushButton, "remove_button")
    remove_button.click()

    assert page.table.rowCount() == 0
    assert store.get(entry.id) is None


def test_open_file_button_disabled_without_file_path(qtbot, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    store.add(_entry(title="No file", file_path=None))

    page = HistoryPage(store)
    qtbot.addWidget(page)

    container = page.table.cellWidget(0, 4)
    open_file_button = container.findChild(QPushButton, "open_file_button")
    open_folder_button = container.findChild(QPushButton, "open_folder_button")
    assert not open_file_button.isEnabled()
    assert not open_folder_button.isEnabled()


def test_open_file_button_calls_qdesktopservices(qtbot, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    store.add(_entry(title="Has file", file_path="/tmp/video.mp4"))

    page = HistoryPage(store)
    qtbot.addWidget(page)

    container = page.table.cellWidget(0, 4)
    open_file_button = container.findChild(QPushButton, "open_file_button")

    with patch("ui.pages.history_page.QDesktopServices.openUrl") as mock_open:
        open_file_button.click()
        mock_open.assert_called_once()


def test_open_folder_button_opens_parent_directory(qtbot, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    store.add(_entry(title="Has file", file_path="/tmp/subdir/video.mp4"))

    page = HistoryPage(store)
    qtbot.addWidget(page)

    container = page.table.cellWidget(0, 4)
    open_folder_button = container.findChild(QPushButton, "open_folder_button")

    with patch("ui.pages.history_page.QDesktopServices.openUrl") as mock_open:
        open_folder_button.click()
        called_url = mock_open.call_args[0][0]
        assert called_url.toLocalFile() == "/tmp/subdir"


def test_redownload_button_emits_signal_with_url(qtbot, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    store.add(_entry(url="https://example.com/redo-me", title="Redo"))

    page = HistoryPage(store)
    qtbot.addWidget(page)

    container = page.table.cellWidget(0, 4)
    redownload_button = container.findChild(QPushButton, "redownload_button")

    with qtbot.waitSignal(page.redownload_requested, timeout=1000) as blocker:
        redownload_button.click()

    assert blocker.args == ["https://example.com/redo-me"]


def test_clear_all_does_nothing_when_empty(qtbot, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    page = HistoryPage(store)
    qtbot.addWidget(page)

    # Should not even prompt (and definitely not crash) with nothing to clear.
    page.clear_all_button.click()
    assert page.table.rowCount() == 0


def test_clear_all_confirmed_empties_store(qtbot, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    store.add(_entry())
    store.add(_entry())

    page = HistoryPage(store)
    qtbot.addWidget(page)

    with patch("ui.pages.history_page.QMessageBox.question", return_value=QMessageBox_Yes()):
        page.clear_all_button.click()

    assert page.table.rowCount() == 0
    assert store.all_entries() == []


def QMessageBox_Yes():
    from PySide6.QtWidgets import QMessageBox

    return QMessageBox.Yes


def test_clear_all_cancelled_keeps_entries(qtbot, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    store = HistoryStore(tmp_path / "history.json")
    store.add(_entry())

    page = HistoryPage(store)
    qtbot.addWidget(page)

    with patch("ui.pages.history_page.QMessageBox.question", return_value=QMessageBox.No):
        page.clear_all_button.click()

    assert page.table.rowCount() == 1
    assert len(store.all_entries()) == 1
