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
    # Both modules hold their own reference to get_app_data_dir; patch both
    # so tests never read the developer's real config.json.
    with patch("utils.paths.get_app_data_dir", return_value=tmp), patch(
        "app.config.get_app_data_dir", return_value=tmp
    ):
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


def test_go_to_navigates_to_settings_tab(qtbot):
    from ui.main_window import NAV_SECTIONS

    window = _make_window()
    qtbot.addWidget(window)

    window.nav_list.setCurrentRow(0)  # start on Download
    window.go_to("Settings")

    assert window.nav_list.currentRow() == NAV_SECTIONS.index("Settings")
    assert window.page_stack.currentWidget() is window.settings_page
    window.download_manager.shutdown()


def test_ctrl_number_shortcuts_switch_pages(qtbot):
    from ui.main_window import NAV_SECTIONS

    window = _make_window()
    qtbot.addWidget(window)

    window._shortcuts[NAV_SECTIONS.index("History")].activated.emit()
    assert window.page_stack.currentWidget() is window.history_page
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


def test_settings_save_passes_ffmpeg_path_to_download_page(qtbot):
    window = _make_window()
    qtbot.addWidget(window)

    window.settings_page.ffmpeg_path_edit.setText("C:/tools/ffmpeg.exe")
    with patch("ui.main_window.save_config"), patch("ui.pages.settings_page.save_config"):
        window.settings_page.save_button.click()

    assert window.download_page._build_final_options()["ffmpeg_location"] == "C:/tools/ffmpeg.exe"
    window.download_manager.shutdown()


def test_window_fits_on_a_small_screen(qtbot):
    """The window must never demand more room than a 1280x720 laptop screen
    offers, and should open at a compact size rather than filling it."""
    from ui.main_window import DEFAULT_WINDOW_SIZE

    window = _make_window()
    qtbot.addWidget(window)
    window.show()

    hint = window.minimumSizeHint()
    assert hint.width() <= 1200 and hint.height() <= 650
    assert window.width() <= DEFAULT_WINDOW_SIZE[0] and window.height() <= DEFAULT_WINDOW_SIZE[1]
    window.download_manager.shutdown()


def test_long_ffmpeg_path_does_not_widen_the_window(qtbot):
    window = _make_window()
    qtbot.addWidget(window)
    window.show()
    window.settings_page.ffmpeg_status_label.setText("✓ Found at C:\\" + "VeryLongDirectoryName\\" * 20 + "ffmpeg.exe")
    assert window.minimumSizeHint().width() <= 1200
    window.download_manager.shutdown()


def test_no_placeholder_pages_in_navigation():
    from ui.main_window import NAV_SECTIONS

    assert "Formats" not in NAV_SECTIONS


def test_default_window_size_scales_with_screen_and_never_fills_it():
    from ui.main_window import DEFAULT_WINDOW_SIZE, MINIMUM_WINDOW_SIZE, default_window_size

    for screen in [(1280, 720), (1366, 728), (1920, 1040), (2560, 1400), (3840, 2100), (1024, 600)]:
        width, height = default_window_size(*screen)
        assert width <= screen[0] * 0.94 + 1 and height <= screen[1] * 0.92 + 1, screen
        assert width >= MINIMUM_WINDOW_SIZE[0] and height >= MINIMUM_WINDOW_SIZE[1]
        assert width <= DEFAULT_WINDOW_SIZE[0] and height <= DEFAULT_WINDOW_SIZE[1]
    # Bigger screens get a bigger (but capped) window.
    assert default_window_size(1920, 1040)[0] > default_window_size(1280, 720)[0]


def test_sidebar_collapses_to_icons_on_narrow_windows(qtbot):
    from ui.main_window import COMPACT_SIDEBAR_BELOW, SIDEBAR_WIDTH_COMPACT

    window = _make_window()
    qtbot.addWidget(window)
    window.show()

    window.resize(COMPACT_SIDEBAR_BELOW - 100, 600)
    qtbot.waitUntil(lambda: window.is_sidebar_compact(), timeout=2000)
    assert window.sidebar.width() == SIDEBAR_WIDTH_COMPACT
    assert window.nav_list.item(0).text() == ""

    window.resize(COMPACT_SIDEBAR_BELOW + 200, 700)
    qtbot.waitUntil(lambda: not window.is_sidebar_compact(), timeout=2000)
    assert window.nav_list.item(0).text() == "Download"
    window.download_manager.shutdown()


def test_window_remembers_its_geometry(qtbot, tmp_path):
    with patch("utils.paths.get_app_data_dir", return_value=tmp_path), patch(
        "app.config.get_app_data_dir", return_value=tmp_path
    ):
        from ui.main_window import MainWindow

        first = MainWindow()
        qtbot.addWidget(first)
        first.show()
        first.resize(900, 600)
        first.close()

        second = MainWindow()
        qtbot.addWidget(second)
    assert (second.width(), second.height()) == (900, 600)
    second.download_manager.shutdown()


def test_queue_badge_tracks_active_downloads(qtbot):
    from ui.main_window import _BADGE_ROLE, NAV_SECTIONS

    window = _make_window()
    qtbot.addWidget(window)
    window.queue_page.active_count_changed.emit(3)
    assert window.nav_list.item(NAV_SECTIONS.index("Queue")).data(_BADGE_ROLE) == 3
    assert "3 downloading" in window.windowTitle()
    window.queue_page.active_count_changed.emit(0)
    assert "downloading" not in window.windowTitle()
    window.download_manager.shutdown()


def test_completed_download_shows_toast_once(qtbot):
    from download.task import DownloadStatus, DownloadTask
    from formats.selector import FormatSelection

    window = _make_window()
    qtbot.addWidget(window)
    window.show()
    task = DownloadTask(url="https://example.com/v", selection=FormatSelection(), output_dir="/tmp",
                        filename_template="%(title)s.%(ext)s", ytdlp_options={}, title="Clip")
    task.status = DownloadStatus.COMPLETED
    with patch.object(window.toast, "show_message") as show:
        window.download_manager.task_updated.emit(task)
        window.download_manager.task_updated.emit(task)
    show.assert_called_once()
    assert "Clip" in show.call_args[0][0]
    window.download_manager.shutdown()


def test_changing_folder_on_download_page_persists_to_config(qtbot):
    window = _make_window()
    qtbot.addWidget(window)
    with patch("ui.main_window.save_config") as save:
        window.download_page.output_dir_changed.emit("D:/Videos")
    assert window.config.download_directory == "D:/Videos"
    assert window.settings_page.download_dir_edit.text() == "D:/Videos"
    save.assert_called_once()
    window.download_manager.shutdown()
