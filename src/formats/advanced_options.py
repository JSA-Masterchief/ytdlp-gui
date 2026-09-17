"""GUI-friendly settings for subtitles, SponsorBlock, chapters, and
metadata/thumbnail embedding, translated into real yt-dlp options and
postprocessor entries.

Every postprocessor 'key' and field name here is copied from yt-dlp's own
CLI-to-options translation (yt_dlp/__init__.py:get_postprocessors) rather
than guessed, so the GUI produces exactly what the yt-dlp command line
would produce for the equivalent flags.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SUBTITLE_MODE_NONE = "none"
SUBTITLE_MODE_MANUAL = "manual"
SUBTITLE_MODE_AUTO = "auto"
SUBTITLE_MODE_ALL = "all"
ALL_SUBTITLE_MODES = (SUBTITLE_MODE_NONE, SUBTITLE_MODE_MANUAL, SUBTITLE_MODE_AUTO, SUBTITLE_MODE_ALL)

# code -> display name, from yt_dlp.postprocessor.sponsorblock.SponsorBlockPP.CATEGORIES
SPONSORBLOCK_CATEGORIES: dict[str, str] = {
    "sponsor": "Sponsor",
    "intro": "Intro",
    "outro": "Outro",
    "selfpromo": "Self-promotion",
    "interaction": "Interaction reminder",
    "preview": "Preview/Recap",
    "filler": "Filler tangent",
}

SPONSORBLOCK_ACTION_REMOVE = "remove"
SPONSORBLOCK_ACTION_MARK = "mark"


@dataclass
class SubtitleOptions:
    mode: str = SUBTITLE_MODE_NONE
    languages: list[str] = field(default_factory=lambda: ["en"])
    embed: bool = False  # burn into the container vs. leave as a sidecar file

    def __post_init__(self) -> None:
        if self.mode not in ALL_SUBTITLE_MODES:
            raise ValueError(f"Unknown subtitle mode: {self.mode}")


@dataclass
class SponsorBlockOptions:
    enabled: bool = False
    action: str = SPONSORBLOCK_ACTION_REMOVE
    categories: list[str] = field(default_factory=lambda: ["sponsor"])

    def __post_init__(self) -> None:
        if self.action not in (SPONSORBLOCK_ACTION_REMOVE, SPONSORBLOCK_ACTION_MARK):
            raise ValueError(f"Unknown SponsorBlock action: {self.action}")
        unknown = set(self.categories) - set(SPONSORBLOCK_CATEGORIES)
        if unknown:
            raise ValueError(f"Unknown SponsorBlock categories: {sorted(unknown)}")


@dataclass
class ChapterOptions:
    embed_chapters: bool = False
    split_chapters: bool = False


@dataclass
class MetadataOptions:
    embed_metadata: bool = False
    embed_thumbnail: bool = False
    write_thumbnail: bool = False


@dataclass
class AdvancedOptions:
    subtitles: SubtitleOptions = field(default_factory=SubtitleOptions)
    sponsorblock: SponsorBlockOptions = field(default_factory=SponsorBlockOptions)
    chapters: ChapterOptions = field(default_factory=ChapterOptions)
    metadata: MetadataOptions = field(default_factory=MetadataOptions)


def apply_advanced_options(options: dict[str, Any], advanced: AdvancedOptions) -> dict[str, Any]:
    """Return a new options dict with `options` plus everything `advanced`
    implies (top-level flags and postprocessor entries), mirroring how
    yt-dlp's own CLI builds these from --write-subs, --sponsorblock-remove,
    --embed-thumbnail, etc.
    """
    opts = dict(options)
    postprocessors: list[dict[str, Any]] = list(opts.get("postprocessors", []))

    subs = advanced.subtitles
    if subs.mode != SUBTITLE_MODE_NONE:
        opts["subtitleslangs"] = list(subs.languages) or ["en"]
        if subs.mode in (SUBTITLE_MODE_MANUAL, SUBTITLE_MODE_ALL):
            opts["writesubtitles"] = True
        if subs.mode in (SUBTITLE_MODE_AUTO, SUBTITLE_MODE_ALL):
            opts["writeautomaticsub"] = True
        if subs.embed:
            postprocessors.append(
                {
                    "key": "FFmpegEmbedSubtitle",
                    "already_have_subtitle": bool(opts.get("writesubtitles")),
                }
            )

    sb = advanced.sponsorblock
    if sb.enabled and sb.categories:
        categories = set(sb.categories)
        postprocessors.append(
            {
                "key": "SponsorBlock",
                "categories": categories,
                "api": "https://sponsor.ajay.app",
                "when": "after_filter",
            }
        )
        if sb.action == SPONSORBLOCK_ACTION_REMOVE:
            postprocessors.append(
                {
                    "key": "ModifyChapters",
                    "remove_chapters_patterns": [],
                    "remove_sponsor_segments": categories,
                    "remove_ranges": [],
                    "sponsorblock_chapter_title": "[SponsorBlock]: %(category_names)l",
                    "force_keyframes": False,
                }
            )
        # action == "mark" needs no ModifyChapters step: SponsorBlock alone
        # attaches the segments as chapter markers without cutting anything.

    chapters = advanced.chapters
    if chapters.split_chapters:
        postprocessors.append({"key": "FFmpegSplitChapters", "force_keyframes": False})

    metadata = advanced.metadata
    if metadata.embed_metadata or chapters.embed_chapters:
        postprocessors.append(
            {
                "key": "FFmpegMetadata",
                "add_chapters": chapters.embed_chapters,
                "add_metadata": metadata.embed_metadata,
                "add_infojson": None,
            }
        )

    if metadata.write_thumbnail:
        opts["writethumbnail"] = True

    if metadata.embed_thumbnail:
        postprocessors.append(
            {
                "key": "EmbedThumbnail",
                "already_have_thumbnail": bool(opts.get("writethumbnail")),
            }
        )
        opts["writethumbnail"] = True

    if postprocessors:
        opts["postprocessors"] = postprocessors

    return opts
