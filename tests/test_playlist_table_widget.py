from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.models import PlaylistEntry, PlaylistInfo
from formats.playlist_selection import PlaylistSelectionMode
from ui.widgets.playlist_table_widget import PlaylistTableWidget, _format_duration

SAMPLE_PLAYLIST = PlaylistInfo(
    id="pl1",
    title="My Playlist",
    uploader="Someone",
    webpage_url="https://example.com/playlist",
    entries=[
        PlaylistEntry(id="v1", title="Video 1", url="https://x/1", duration=65, index=1),
        PlaylistEntry(id="v2", title="Video 2", url="https://x/2", duration=125, index=2),
        PlaylistEntry(id="v3", title="Video 3", url="https://x/3", duration=None, index=3),
    ],
)


def test_format_duration():
    assert _format_duration(65) == "1:05"
    assert _format_duration(3725) == "1:02:05"
    assert _format_duration(None) == ""


def test_load_playlist_populates_table(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)

    widget.load_playlist(SAMPLE_PLAYLIST)

    assert widget.table.rowCount() == 3
    assert widget.table.item(0, 2).text() == "Video 1"
    assert widget.table.item(0, 3).text() == "1:05"
    assert widget.table.item(1, 1).text() == "2"


def test_all_checkboxes_checked_by_default(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)
    widget.load_playlist(SAMPLE_PLAYLIST)

    options = widget.current_options()
    assert options.mode == PlaylistSelectionMode.ALL


def test_default_mode_downloads_everything_regardless_of_checkboxes(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)
    widget.load_playlist(SAMPLE_PLAYLIST)

    widget._checkboxes[2].setChecked(False)  # unchecking shouldn't matter in ALL mode
    options = widget.current_options()
    assert options.mode == PlaylistSelectionMode.ALL


def test_selected_mode_reflects_checked_boxes(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)
    widget.load_playlist(SAMPLE_PLAYLIST)

    widget.mode_selected_radio.setChecked(True)
    widget._checkboxes[2].setChecked(False)

    options = widget.current_options()
    assert options.mode == PlaylistSelectionMode.SELECTED
    assert options.selected_indices == {1, 3}


def test_select_all_and_select_none_buttons(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)
    widget.load_playlist(SAMPLE_PLAYLIST)
    widget.mode_selected_radio.setChecked(True)

    widget.select_none_button.click()
    assert widget.current_options().selected_indices == set()

    widget.select_all_button.click()
    assert widget.current_options().selected_indices == {1, 2, 3}


def test_range_mode_bounds_reflect_playlist_size(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)
    widget.load_playlist(SAMPLE_PLAYLIST)

    assert widget.range_end_spin.value() == 3
    assert widget.range_end_spin.maximum() == 3


def test_range_mode_options(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)
    widget.load_playlist(SAMPLE_PLAYLIST)

    widget.mode_range_radio.setChecked(True)
    widget.range_start_spin.setValue(2)
    widget.range_end_spin.setValue(3)

    options = widget.current_options()
    assert options.mode == PlaylistSelectionMode.RANGE
    assert options.range_start == 2
    assert options.range_end == 3


def test_reverse_checkbox_reflected_in_options(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)
    widget.load_playlist(SAMPLE_PLAYLIST)

    widget.reverse_checkbox.setChecked(True)
    assert widget.current_options().reverse is True


def test_archive_controls_disabled_until_skip_archived_checked(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)

    assert not widget.archive_path_edit.isEnabled()
    assert not widget.archive_browse_button.isEnabled()

    widget.skip_archived_checkbox.setChecked(True)

    assert widget.archive_path_edit.isEnabled()
    assert widget.archive_browse_button.isEnabled()


def test_archive_path_reflected_in_options(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)
    widget.skip_archived_checkbox.setChecked(True)
    widget.archive_path_edit.setText("/tmp/archive.txt")

    options = widget.current_options()
    assert options.skip_archived is True
    assert options.archive_path == "/tmp/archive.txt"


def test_set_entry_status_updates_the_right_row(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)
    widget.load_playlist(SAMPLE_PLAYLIST)

    widget.set_entry_status("v2", "Downloading")

    assert widget.table.item(1, 4).text() == "Downloading"
    assert widget.table.item(0, 4).text() == ""


def test_selection_changed_signal_fires_on_checkbox_toggle(qtbot):
    widget = PlaylistTableWidget()
    qtbot.addWidget(widget)
    widget.load_playlist(SAMPLE_PLAYLIST)

    with qtbot.waitSignal(widget.selection_changed, timeout=1000):
        widget._checkboxes[1].setChecked(False)
