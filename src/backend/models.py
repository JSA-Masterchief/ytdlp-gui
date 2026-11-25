"""Plain dataclasses representing yt-dlp results."""

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
    abr: float | None = None
    vbr: float | None = None
    filesize: int | None = None
    filesize_approx: int | None = None
    dynamic_range: str | None = None
    note: str | None = None

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
    id: str
    title: str
    webpage_url: str
    extractor: str
    duration: float | None = None
    uploader: str | None = None
    upload_date: str | None = None
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
