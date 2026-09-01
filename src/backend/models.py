"""Plain dataclasses representing yt-dlp results.

The rest of the app (UI, queue, history) should only ever see these types,
never yt-dlp's raw info-dicts. This keeps the UI layer stable if yt-dlp's
internal dict shape changes between versions.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FormatInfo:
    format_id: str
    ext: str
    resolution: str | None = None
    fps: float | None = None
    vcodec: str | None = None
    acodec: str | None = None
    abr: float | None = None  # audio bitrate, kbps
    vbr: float | None = None  # video bitrate, kbps
    filesize: int | None = None  # bytes, may be None if unknown/estimated
    filesize_approx: int | None = None
    dynamic_range: str | None = None  # e.g. "HDR10"
    note: str | None = None  # yt-dlp's human "format_note" (e.g. "1080p60")

    @property
    def is_video_only(self) -> bool:
        return self.vcodec not in (None, "none") and self.acodec in (None, "none")

    @property
    def is_audio_only(self) -> bool:
        return self.acodec not in (None, "none") and self.vcodec in (None, "none")

    @property
    def is_combined(self) -> bool:
        return self.vcodec not in (None, "none") and self.acodec not in (None, "none")


@dataclass
class MediaInfo:
    """A single downloadable item (a video, not a playlist)."""

    id: str
    title: str
    webpage_url: str
    extractor: str
    duration: float | None = None  # seconds
    uploader: str | None = None
    upload_date: str | None = None  # yt-dlp format: YYYYMMDD
    view_count: int | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    formats: list[FormatInfo] = field(default_factory=list)
    subtitle_languages: list[str] = field(default_factory=list)
    automatic_caption_languages: list[str] = field(default_factory=list)


@dataclass
class PlaylistEntry:
    id: str
    title: str
    url: str
    duration: float | None = None
    index: int | None = None


@dataclass
class PlaylistInfo:
    id: str
    title: str
    uploader: str | None
    webpage_url: str
    entries: list[PlaylistEntry] = field(default_factory=list)

    @property
    def entry_count(self) -> int:
        return len(self.entries)
