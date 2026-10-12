from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _make_window():
    """Build a MainWindow against an isolated temp app-data dir so tests
    never touch the real config/history/log files on disk.
    """
    tmp = Path(tempfile.mkdtemp())
    with patch("utils.paths.get_app_data_dir", return_value=tmp):
        from ui.main_window import MainWindow

        window = MainWindow()
    return window


def test_theme_toggle_cycles_through_system_light_dark(qtbot):
    window = _make_window()
    qtbot.addWidget(window)

    assert window.config.theme == "system"
    assert "System" in window.theme_toggle_button.text()

    with patch("ui.main_window.save_config"):
        window.theme_toggle_button.click()
        assert window.config.theme == "light"
        assert "Light" in window.theme_toggle_button.text()

        window.theme_toggle_button.click()
        assert window.config.theme == "dark"
        assert "Dark" in window.theme_toggle_button.text()

        window.theme_toggle_button.click()
        assert window.config.theme == "system"

    window.download_manager.shutdown()


def test_theme_toggle_persists_via_save_config(qtbot):
    window = _make_window()
    qtbot.addWidget(window)

    with patch("ui.main_window.save_config") as mock_save:
        window.theme_toggle_button.click()
        mock_save.assert_called_once()
        assert mock_save.call_args[0][0].theme == "light"

    window.download_manager.shutdown()


def test_theme_toggle_updates_settings_page_combo(qtbot):
    window = _make_window()
    qtbot.addWidget(window)

    with patch("ui.main_window.save_config"):
        window.theme_toggle_button.click()

    assert window.settings_page.theme_combo.currentData() == "light"
    window.download_manager.shutdown()


def test_settings_button_navigates_to_settings_tab(qtbot):
    window = _make_window()
    qtbot.addWidget(window)

    window.nav_list.setCurrentRow(0)  # start on Download
    window.settings_button.click()

    assert window.nav_list.currentRow() == 4  # Settings is index 4 in NAV_SECTIONS
    window.download_manager.shutdown()


def test_about_button_shows_dialog(qtbot):
    window = _make_window()
    qtbot.addWidget(window)

    with patch("ui.main_window.QMessageBox.about") as mock_about:
        window.about_button.click()
        mock_about.assert_called_once()
        # The disclaimer language from the spec must actually be present.
        shown_text = mock_about.call_args[0][2]
        assert "DRM" in shown_text

    window.download_manager.shutdown()


def test_settings_save_applies_theme_live(qtbot):
    window = _make_window()
    qtbot.addWidget(window)

    idx = window.settings_page.theme_combo.findData("dark")
    window.settings_page.theme_combo.setCurrentIndex(idx)

    with patch("ui.main_window.save_config"), patch("ui.pages.settings_page.save_config"), patch(
        "ui.main_window.apply_theme"
    ) as mock_apply:
        window.settings_page.save_button.click()

    assert window.config.theme == "dark"
    mock_apply.assert_called_once()

    window.download_manager.shutdown()
