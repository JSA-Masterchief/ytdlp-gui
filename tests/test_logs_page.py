from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ui.pages.logs_page import LogsPage


def test_loads_existing_log_content(qtbot, tmp_path):
    log_path = tmp_path / "app.log"
    log_path.write_text("line one\nline two\n", encoding="utf-8")

    page = LogsPage(log_path)
    qtbot.addWidget(page)

    assert "line one" in page.text_view.toPlainText()
    assert "line two" in page.text_view.toPlainText()


def test_missing_log_file_shows_placeholder_without_crashing(qtbot, tmp_path):
    page = LogsPage(tmp_path / "does_not_exist.log")
    qtbot.addWidget(page)

    assert "no log file" in page.text_view.toPlainText().lower()


def test_refresh_picks_up_new_content(qtbot, tmp_path):
    log_path = tmp_path / "app.log"
    log_path.write_text("first\n", encoding="utf-8")

    page = LogsPage(log_path)
    qtbot.addWidget(page)
    assert "first" in page.text_view.toPlainText()

    log_path.write_text("first\nsecond\n", encoding="utf-8")
    page.refresh_button.click()

    assert "second" in page.text_view.toPlainText()


def test_search_filters_to_matching_lines_only(qtbot, tmp_path):
    log_path = tmp_path / "app.log"
    log_path.write_text("INFO starting up\nERROR something broke\nINFO still running\n", encoding="utf-8")

    page = LogsPage(log_path)
    qtbot.addWidget(page)

    page.search_edit.setText("ERROR")
    text = page.text_view.toPlainText()
    assert "something broke" in text
    assert "starting up" not in text
    assert "still running" not in text


def test_clearing_search_restores_full_log(qtbot, tmp_path):
    log_path = tmp_path / "app.log"
    log_path.write_text("INFO one\nERROR two\n", encoding="utf-8")

    page = LogsPage(log_path)
    qtbot.addWidget(page)

    page.search_edit.setText("ERROR")
    page.search_edit.setText("")

    assert "one" in page.text_view.toPlainText()
    assert "two" in page.text_view.toPlainText()


def test_clear_button_confirmed_empties_the_real_file(qtbot, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    log_path = tmp_path / "app.log"
    log_path.write_text("some log content\n", encoding="utf-8")

    page = LogsPage(log_path)
    qtbot.addWidget(page)

    with patch("ui.pages.logs_page.QMessageBox.question", return_value=QMessageBox.Yes):
        page.clear_button.click()

    assert log_path.read_text(encoding="utf-8") == ""
    assert page.text_view.toPlainText() == ""


def test_clear_button_cancelled_leaves_file_untouched(qtbot, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    log_path = tmp_path / "app.log"
    log_path.write_text("keep this\n", encoding="utf-8")

    page = LogsPage(log_path)
    qtbot.addWidget(page)

    with patch("ui.pages.logs_page.QMessageBox.question", return_value=QMessageBox.No):
        page.clear_button.click()

    assert log_path.read_text(encoding="utf-8") == "keep this\n"


def test_copy_button_sets_clipboard(qtbot, tmp_path):
    log_path = tmp_path / "app.log"
    log_path.write_text("copy me\n", encoding="utf-8")

    page = LogsPage(log_path)
    qtbot.addWidget(page)

    with patch("ui.pages.logs_page.QApplication.clipboard") as mock_clipboard:
        page.copy_button.click()
        mock_clipboard.return_value.setText.assert_called_once()
        assert "copy me" in mock_clipboard.return_value.setText.call_args[0][0]


def test_save_button_writes_filtered_text_to_chosen_path(qtbot, tmp_path):
    log_path = tmp_path / "app.log"
    log_path.write_text("line a\nline b\n", encoding="utf-8")
    save_path = tmp_path / "exported.log"

    page = LogsPage(log_path)
    qtbot.addWidget(page)

    with patch("ui.pages.logs_page.QFileDialog.getSaveFileName", return_value=(str(save_path), "")):
        page.save_button.click()

    assert save_path.read_text(encoding="utf-8") == "line a\nline b\n"


def test_save_button_cancelled_dialog_writes_nothing(qtbot, tmp_path):
    log_path = tmp_path / "app.log"
    log_path.write_text("line a\n", encoding="utf-8")
    save_path = tmp_path / "should_not_exist.log"

    page = LogsPage(log_path)
    qtbot.addWidget(page)

    with patch("ui.pages.logs_page.QFileDialog.getSaveFileName", return_value=("", "")):
        page.save_button.click()

    assert not save_path.exists()
