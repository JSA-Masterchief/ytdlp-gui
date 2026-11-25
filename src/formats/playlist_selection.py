"""Turns a playlist selection made in the GUI into the ordered list of
entries to actually download. One ordinary DownloadTask is created per
selected entry (using that entry's own video URL) rather than passing the
playlist URL with playlist_items/playliststart to yt-dlp directly, so
playlists reuse all the existing single-video queue/progress/cancel/retry
machinery and give the Queue page real per-item progress.
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
    selected_indices: set[int] = field(default_factory=set)
    range_start: int = 1
    range_end: int | None = None
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
    Never overwrites an existing download_archive value already present
    (e.g. from a --download-archive typed into Custom Arguments).
    """
    opts = dict(ytdlp_options)
    if playlist_options.skip_archived and playlist_options.archive_path and "download_archive" not in opts:
        opts["download_archive"] = playlist_options.archive_path
    return opts
