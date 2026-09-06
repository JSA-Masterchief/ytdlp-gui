from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.models import MediaInfo, PlaylistInfo
from ui.widgets.metadata_panel import MetadataPanel, _format_duration, _format_view_count


def test_format_duration_under_an_hour():
    assert _format_duration(125) == "2:05"


def test_format_duration_over_an_hour():
    assert _format_duration(3725) == "1:02:05"


def test_format_duration_none():
    assert _format_duration(None) == "Unknown length"


def test_format_view_count_millions():
    assert _format_view_count(2_500_000) == "2.5M views"


def test_format_view_count_thousands():
    assert _format_view_count(1_500) == "1.5K views"


def test_format_view_count_small():
    assert _format_view_count(42) == "42 views"


def test_panel_shows_media_info(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)

    info = MediaInfo(
        id="abc",
        title="My Video",
        webpage_url="https://example.com",
        extractor="youtube",
        duration=90,
        uploader="Channel Name",
        view_count=1000,
    )
    panel.show_media(info)

    assert panel.title_label.text() == "My Video"
    assert "Channel Name" in panel.subtitle_label.text()
    assert "1:30" in panel.subtitle_label.text()


def test_panel_shows_playlist_info(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)

    info = PlaylistInfo(id="pl1", title="My Playlist", uploader="Someone", webpage_url="https://example.com")
    panel.show_playlist(info)

    assert panel.title_label.text() == "My Playlist"
    assert "0" in panel.detail_label.text()


def test_panel_shows_error(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)

    panel.show_error("Video unavailable.")

    assert "failed" in panel.title_label.text().lower()
    assert panel.detail_label.text() == "Video unavailable."
