"""Turns a playlist selection made in the GUI (entire playlist / specific
checkboxes / an index range, optionally reversed) into the ordered list of
entries to actually download.

Design note: rather than passing the playlist URL itself to yt-dlp with
playlist_items/playliststart/playlistend options and letting yt-dlp select
internally, this app resolves the entry list here and creates one ordinary
DownloadTask per selected entry (using that entry's own video URL). That
reuses all of the existing single-video queue/progress/cancel/retry
machinery from download/manager.py for playlists too, and gives the Queue
page real per-item progress instead of one opaque "downloading a playlist"
row — matching the "playlist item table with per-item status" requirement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from backend.models import PlaylistEntry


class PlaylistSelectionMode(str, Enum):
    ALL = "all"
    SELECTED = "selected"
    RANGE = "range"


@dataclass
class PlaylistDownloadOptions:
    mode: PlaylistSelectionMode = PlaylistSelectionMode.ALL
    selected_indices: set[int] = field(default_factory=set)  # 1-based, used when mode == SELECTED
    range_start: int = 1
    range_end: int | None = None  # None means "through the last entry"
    reverse: bool = False
    skip_archived: bool = False
    archive_path: str | None = None

    def __post_init__(self) -> None:
        if self.range_start < 1:
            raise ValueError("range_start must be >= 1")
        if self.range_end is not None and self.range_end < self.range_start:
            raise ValueError("range_end must be >= range_start")


def resolve_selected_entries(
    entries: list[PlaylistEntry],
    options: PlaylistDownloadOptions,
) -> list[PlaylistEntry]:
    """Return the ordered list of entries to download for this selection.
    Entries with no index (shouldn't normally happen — see
    YtdlpBackend._playlist_from_info) are excluded from range/selected
    modes since there is nothing to match against, but always included
    under ALL.
    """
    if options.mode == PlaylistSelectionMode.ALL:
        selected = list(entries)
    elif options.mode == PlaylistSelectionMode.SELECTED:
        selected = [e for e in entries if e.index is not None and e.index in options.selected_indices]
    elif options.mode == PlaylistSelectionMode.RANGE:
        end = options.range_end if options.range_end is not None else len(entries)
        selected = [e for e in entries if e.index is not None and options.range_start <= e.index <= end]
    else:
        raise ValueError(f"Unknown playlist selection mode: {options.mode}")

    if options.reverse:
        selected = list(reversed(selected))

    return selected


def apply_archive_option(ytdlp_options: dict, playlist_options: PlaylistDownloadOptions) -> dict:
    """Return a copy of ytdlp_options with download_archive set, if the
    user asked to skip already-downloaded items and gave an archive path.
    yt-dlp treats this as a real file it reads before, and appends to
    after, each download — pointing every generated task at the same path
    is what makes "skip already downloaded" work across a playlist.
    """
    opts = dict(ytdlp_options)
    if playlist_options.skip_archived and playlist_options.archive_path:
        opts["download_archive"] = playlist_options.archive_path
    return opts
