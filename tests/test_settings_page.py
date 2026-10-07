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
