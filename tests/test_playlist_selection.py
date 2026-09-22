from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.models import PlaylistEntry
from formats.playlist_selection import (
    PlaylistDownloadOptions,
    PlaylistSelectionMode,
    apply_archive_option,
    resolve_selected_entries,
)

ENTRIES = [
    PlaylistEntry(id="v1", title="Video 1", url="https://x/1", index=1),
    PlaylistEntry(id="v2", title="Video 2", url="https://x/2", index=2),
    PlaylistEntry(id="v3", title="Video 3", url="https://x/3", index=3),
    PlaylistEntry(id="v4", title="Video 4", url="https://x/4", index=4),
    PlaylistEntry(id="v5", title="Video 5", url="https://x/5", index=5),
]


class TestPlaylistDownloadOptionsValidation:
    def test_range_start_below_one_raises(self):
        with pytest.raises(ValueError):
            PlaylistDownloadOptions(mode=PlaylistSelectionMode.RANGE, range_start=0)

    def test_range_end_before_start_raises(self):
        with pytest.raises(ValueError):
            PlaylistDownloadOptions(mode=PlaylistSelectionMode.RANGE, range_start=5, range_end=2)

    def test_valid_range_does_not_raise(self):
        PlaylistDownloadOptions(mode=PlaylistSelectionMode.RANGE, range_start=2, range_end=4)


class TestResolveAll:
    def test_all_mode_returns_every_entry_in_order(self):
        options = PlaylistDownloadOptions(mode=PlaylistSelectionMode.ALL)
        result = resolve_selected_entries(ENTRIES, options)
        assert [e.id for e in result] == ["v1", "v2", "v3", "v4", "v5"]

    def test_all_mode_reversed(self):
        options = PlaylistDownloadOptions(mode=PlaylistSelectionMode.ALL, reverse=True)
        result = resolve_selected_entries(ENTRIES, options)
        assert [e.id for e in result] == ["v5", "v4", "v3", "v2", "v1"]


class TestResolveSelected:
    def test_selected_mode_returns_only_checked_indices(self):
        options = PlaylistDownloadOptions(mode=PlaylistSelectionMode.SELECTED, selected_indices={1, 3, 5})
        result = resolve_selected_entries(ENTRIES, options)
        assert [e.id for e in result] == ["v1", "v3", "v5"]

    def test_selected_mode_with_no_indices_returns_empty(self):
        options = PlaylistDownloadOptions(mode=PlaylistSelectionMode.SELECTED, selected_indices=set())
        result = resolve_selected_entries(ENTRIES, options)
        assert result == []

    def test_selected_mode_ignores_out_of_range_indices(self):
        options = PlaylistDownloadOptions(mode=PlaylistSelectionMode.SELECTED, selected_indices={99})
        result = resolve_selected_entries(ENTRIES, options)
        assert result == []


class TestResolveRange:
    def test_range_returns_inclusive_slice(self):
        options = PlaylistDownloadOptions(mode=PlaylistSelectionMode.RANGE, range_start=2, range_end=4)
        result = resolve_selected_entries(ENTRIES, options)
        assert [e.id for e in result] == ["v2", "v3", "v4"]

    def test_range_with_no_end_goes_to_last_entry(self):
        options = PlaylistDownloadOptions(mode=PlaylistSelectionMode.RANGE, range_start=3, range_end=None)
        result = resolve_selected_entries(ENTRIES, options)
        assert [e.id for e in result] == ["v3", "v4", "v5"]

    def test_range_reversed(self):
        options = PlaylistDownloadOptions(mode=PlaylistSelectionMode.RANGE, range_start=1, range_end=3, reverse=True)
        result = resolve_selected_entries(ENTRIES, options)
        assert [e.id for e in result] == ["v3", "v2", "v1"]


class TestArchiveOption:
    def test_skip_archived_off_leaves_options_untouched(self):
        options = PlaylistDownloadOptions(skip_archived=False, archive_path="/tmp/archive.txt")
        result = apply_archive_option({"format": "best"}, options)
        assert "download_archive" not in result

    def test_skip_archived_without_path_leaves_options_untouched(self):
        options = PlaylistDownloadOptions(skip_archived=True, archive_path=None)
        result = apply_archive_option({"format": "best"}, options)
        assert "download_archive" not in result

    def test_skip_archived_with_path_sets_download_archive(self):
        options = PlaylistDownloadOptions(skip_archived=True, archive_path="/tmp/archive.txt")
        result = apply_archive_option({"format": "best"}, options)
        assert result["download_archive"] == "/tmp/archive.txt"

    def test_does_not_mutate_the_original_dict(self):
        original = {"format": "best"}
        options = PlaylistDownloadOptions(skip_archived=True, archive_path="/tmp/archive.txt")
        apply_archive_option(original, options)
        assert "download_archive" not in original


class TestRealYtDlpArchiveBehavior:
    def test_real_yt_dlp_respects_download_archive_across_two_instances(self, tmp_path):
        """The full point of the archive feature: a video recorded by one
        YoutubeDL instance must be recognized as already-downloaded by a
        second, separate instance pointed at the same file — exactly the
        "skip already downloaded items" behavior the playlist UI promises.
        """
        import yt_dlp

        archive_path = str(tmp_path / "archive.txt")
        options = PlaylistDownloadOptions(skip_archived=True, archive_path=archive_path)
        opts = apply_archive_option({"quiet": True, "skip_download": True}, options)

        info = {"id": "xyz789", "ie_key": "Youtube", "extractor": "youtube"}

        with yt_dlp.YoutubeDL(opts) as first:
            assert first.in_download_archive(info) is False
            first.record_download_archive(info)

        with yt_dlp.YoutubeDL(opts) as second:
            assert second.in_download_archive(info) is True
