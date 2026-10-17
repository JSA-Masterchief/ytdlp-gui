from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.config import AppConfig
from backend.ffmpeg_manager import ExecutableStatus
from ui.pages.settings_page import SettingsPage

FFMPEG_FOUND = ExecutableStatus(name="ffmpeg", path="/usr/bin/ffmpeg", found=True, version="ffmpeg 6.1")
FFMPEG_MISSING = ExecutableStatus(name="ffmpeg", path=None, found=False, error="not found")


def _patched_ffmpeg(found: bool):
    status = FFMPEG_FOUND if found else FFMPEG_MISSING
    return patch("ui.pages.settings_page.check_ffmpeg", return_value=status), patch(
        "ui.pages.settings_page.check_ffprobe", return_value=status
    )


def test_fields_prefilled_from_config(qtbot):
    config = AppConfig(theme="dark", download_directory="/tmp/downloads", max_concurrent_downloads=3, filename_template="%(id)s.%(ext)s")
    p1, p2 = _patched_ffmpeg(True)
    with p1, p2:
        page = SettingsPage(config)
    qtbot.addWidget(page)

    assert page.theme_combo.currentData() == "dark"
    assert page.download_dir_edit.text() == "/tmp/downloads"
    assert page.max_concurrent_spin.value() == 3
    assert page.filename_template_edit.text() == "%(id)s.%(ext)s"


def test_ffmpeg_found_shows_green_status(qtbot):
    config = AppConfig()
    p1, p2 = _patched_ffmpeg(True)
    with p1, p2:
        page = SettingsPage(config)
    qtbot.addWidget(page)

    assert "Found at" in page.ffmpeg_status_label.text()


def test_ffmpeg_missing_shows_warning(qtbot):
    config = AppConfig()
    p1, p2 = _patched_ffmpeg(False)
    with p1, p2:
        page = SettingsPage(config)
    qtbot.addWidget(page)

    assert "not found" in page.ffmpeg_status_label.text().lower()


def test_current_config_reflects_edited_fields(qtbot):
    config = AppConfig(theme="system", max_concurrent_downloads=2)
    p1, p2 = _patched_ffmpeg(True)
    with p1, p2:
        page = SettingsPage(config)
    qtbot.addWidget(page)

    idx = page.theme_combo.findData("dark")
    page.theme_combo.setCurrentIndex(idx)
    page.max_concurrent_spin.setValue(5)
    page.filename_template_edit.setText("%(title)s.%(ext)s")

    new_config = page.current_config()
    assert new_config.theme == "dark"
    assert new_config.max_concurrent_downloads == 5
    assert new_config.filename_template == "%(title)s.%(ext)s"


def test_empty_download_dir_falls_back_to_existing_value(qtbot):
    config = AppConfig(download_directory="/tmp/original")
    p1, p2 = _patched_ffmpeg(True)
    with p1, p2:
        page = SettingsPage(config)
    qtbot.addWidget(page)

    page.download_dir_edit.setText("")
    assert page.current_config().download_directory == "/tmp/original"


def test_save_button_persists_and_emits_signal(qtbot, tmp_path):
    config = AppConfig(theme="system")
    p1, p2 = _patched_ffmpeg(True)
    with p1, p2:
        page = SettingsPage(config)
    qtbot.addWidget(page)

    idx = page.theme_combo.findData("dark")
    page.theme_combo.setCurrentIndex(idx)

    fake_config_path = tmp_path / "config.json"
    with patch("ui.pages.settings_page.save_config") as mock_save:
        with qtbot.waitSignal(page.settings_saved, timeout=1000) as blocker:
            page.save_button.click()
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]
        assert saved_config.theme == "dark"

    assert blocker.args[0].theme == "dark"
    assert not page.saved_label.isHidden()


def test_refresh_ffmpeg_button_updates_status(qtbot):
    config = AppConfig()
    p1, p2 = _patched_ffmpeg(False)
    with p1, p2:
        page = SettingsPage(config)
    qtbot.addWidget(page)
    assert "not found" in page.ffmpeg_status_label.text().lower()

    p1, p2 = _patched_ffmpeg(True)
    with p1, p2:
        page._refresh_ffmpeg_status()
    assert "Found at" in page.ffmpeg_status_label.text()


# --- filename template presets & validation ---------------------------------

from formats.filename_templates import CUSTOM_PRESET_KEY, FILENAME_TEMPLATE_PRESETS  # noqa: E402


def _page(qtbot, config=None):
    p1, p2 = _patched_ffmpeg(True)
    with p1, p2:
        page = SettingsPage(config or AppConfig())
    qtbot.addWidget(page)
    return page


def test_preset_dropdown_lists_every_preset_plus_custom(qtbot):
    page = _page(qtbot)
    keys = [page.template_preset_combo.itemData(i) for i in range(page.template_preset_combo.count())]
    assert keys == [*FILENAME_TEMPLATE_PRESETS.keys(), CUSTOM_PRESET_KEY]


def test_loading_a_preset_template_preselects_that_preset(qtbot):
    _label, template = FILENAME_TEMPLATE_PRESETS["title_uploader"]
    page = _page(qtbot, AppConfig(filename_template=template))
    assert page.template_preset_combo.currentData() == "title_uploader"


def test_loading_an_unrecognised_template_preselects_custom(qtbot):
    page = _page(qtbot, AppConfig(filename_template="%(id)s/%(title)s.%(ext)s"))
    assert page.template_preset_combo.currentData() == CUSTOM_PRESET_KEY


def test_choosing_a_preset_fills_the_template_field(qtbot):
    page = _page(qtbot)
    idx = page.template_preset_combo.findData("date_title")
    page.template_preset_combo.setCurrentIndex(idx)
    assert page.filename_template_edit.text() == FILENAME_TEMPLATE_PRESETS["date_title"][1]
    assert page.template_preset_combo.currentData() == "date_title"


def test_choosing_custom_leaves_the_text_untouched(qtbot):
    page = _page(qtbot)
    page.filename_template_edit.setText("%(id)s.%(ext)s")
    before = page.filename_template_edit.text()
    page.template_preset_combo.setCurrentIndex(page.template_preset_combo.findData(CUSTOM_PRESET_KEY))
    assert page.filename_template_edit.text() == before


def test_typing_a_preset_template_switches_dropdown_to_it(qtbot):
    page = _page(qtbot)
    page.filename_template_edit.setText(FILENAME_TEMPLATE_PRESETS["title"][1])
    assert page.template_preset_combo.currentData() == "title"


def test_typing_a_custom_template_switches_dropdown_to_custom(qtbot):
    page = _page(qtbot)
    page.filename_template_edit.setText("%(uploader)s/%(id)s.%(ext)s")
    assert page.template_preset_combo.currentData() == CUSTOM_PRESET_KEY


def test_editing_a_preset_into_custom_does_not_get_overwritten(qtbot):
    """Regression guard for a feedback loop: syncing the dropdown from the
    text must not re-fire the preset handler and clobber what was typed.
    """
    page = _page(qtbot)
    page.template_preset_combo.setCurrentIndex(page.template_preset_combo.findData("title"))
    page.filename_template_edit.setText("%(title)s - edited.%(ext)s")
    assert page.filename_template_edit.text() == "%(title)s - edited.%(ext)s"
    assert page.template_preset_combo.currentData() == CUSTOM_PRESET_KEY


def test_valid_template_shows_no_status_message(qtbot):
    page = _page(qtbot)
    page.filename_template_edit.setText("%(title)s.%(ext)s")
    assert page.template_status_label.isHidden()


def test_invalid_template_shows_error(qtbot):
    page = _page(qtbot)
    page.filename_template_edit.setText("%(title")
    assert not page.template_status_label.isHidden()
    assert "Invalid template" in page.template_status_label.text()


def test_template_without_extension_shows_warning(qtbot):
    page = _page(qtbot)
    page.filename_template_edit.setText("%(title)s")
    assert not page.template_status_label.isHidden()
    assert "extension" in page.template_status_label.text().lower()


def test_save_is_blocked_for_an_invalid_template(qtbot):
    page = _page(qtbot)
    page.filename_template_edit.setText("%(title")

    with patch("ui.pages.settings_page.save_config") as mock_save:
        emitted = []
        page.settings_saved.connect(emitted.append)
        page.save_button.click()

    mock_save.assert_not_called()
    assert emitted == []
    assert "Fix the filename template" in page.saved_label.text()


def test_save_succeeds_again_after_fixing_the_template(qtbot):
    page = _page(qtbot)
    page.filename_template_edit.setText("%(title")
    page.save_button.click()  # blocked

    page.filename_template_edit.setText("%(title)s.%(ext)s")
    with patch("ui.pages.settings_page.save_config") as mock_save:
        page.save_button.click()

    mock_save.assert_called_once()
    assert page.saved_label.text() == "Settings saved."


def test_save_with_missing_extension_warning_still_saves(qtbot):
    page = _page(qtbot)
    page.filename_template_edit.setText("%(title)s")  # legal, just warned about
    with patch("ui.pages.settings_page.save_config") as mock_save:
        page.save_button.click()
    mock_save.assert_called_once()
