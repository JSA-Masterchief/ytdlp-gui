"""Maps simple GUI choices to real yt-dlp format-selector syntax and options."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODE_VIDEO_AUDIO = "video_audio"
MODE_VIDEO_ONLY = "video_only"
MODE_AUDIO_ONLY = "audio_only"
ALL_MODES = (MODE_VIDEO_AUDIO, MODE_VIDEO_ONLY, MODE_AUDIO_ONLY)

QUALITY_BEST = "best"
QUALITY_HEIGHTS: dict[str, int] = {
    "2160p": 2160,
    "1440p": 1440,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}

VIDEO_CONTAINERS = ("mp4", "mkv", "webm")
AUDIO_EXTRACT_FORMATS = ("mp3", "m4a", "wav", "opus", "flac")
AUDIO_FORMAT_BEST = "best"
ALL_AUDIO_FORMATS = (AUDIO_FORMAT_BEST, *AUDIO_EXTRACT_FORMATS)

_CONTAINER_AUDIO_EXT = {"mp4": "m4a", "webm": "webm", "mkv": "m4a"}


@dataclass
class FormatSelection:
    mode: str = MODE_VIDEO_AUDIO
    quality: str = QUALITY_BEST
    container: str = "mp4"
    audio_format: str = AUDIO_FORMAT_BEST
    custom_format_string: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in ALL_MODES:
            raise ValueError(f"Unknown mode: {self.mode}")
        if self.quality != QUALITY_BEST and self.quality not in QUALITY_HEIGHTS:
            raise ValueError(f"Unknown quality: {self.quality}")
        if self.audio_format not in ALL_AUDIO_FORMATS:
            raise ValueError(f"Unknown audio format: {self.audio_format}")


def _height_filter(quality: str) -> str:
    if quality == QUALITY_BEST or quality not in QUALITY_HEIGHTS:
        return ""
    return f"[height<={QUALITY_HEIGHTS[quality]}]"


def build_format_string(selection: FormatSelection) -> str:
    if selection.custom_format_string:
        return selection.custom_format_string

    height = _height_filter(selection.quality)

    if selection.mode == MODE_AUDIO_ONLY:
        return "ba/b"

    if selection.mode == MODE_VIDEO_ONLY:
        return f"bv*{height}/wv*{height}"

    if selection.container in VIDEO_CONTAINERS:
        audio_ext = _CONTAINER_AUDIO_EXT.get(selection.container, "m4a")
        return f"bv*{height}[ext={selection.container}]+ba[ext={audio_ext}]/b{height}[ext={selection.container}]/b{height}"

    return f"bv*{height}+ba/b{height}"


def build_ytdlp_options(
    selection: FormatSelection,
    output_dir: str,
    filename_template: str,
    advanced: Any | None = None,
) -> dict[str, Any]:
    """Build the options dict to hand to YtdlpBackend.download().

    `advanced`, if given, is a formats.advanced_options.AdvancedOptions.
    Typed as Any here (rather than imported) to avoid a circular import —
    advanced_options.py has no need to import selector.py, and importing
    it here at module load time would create one for no benefit.
    """
    options: dict[str, Any] = {
        "format": build_format_string(selection),
        "outtmpl": str(Path(output_dir) / filename_template),
    }

    if selection.mode == MODE_AUDIO_ONLY and selection.audio_format != AUDIO_FORMAT_BEST:
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": selection.audio_format,
                "preferredquality": "0",
            }
        ]
    elif selection.mode == MODE_VIDEO_AUDIO and selection.container in VIDEO_CONTAINERS:
        options["merge_output_format"] = selection.container

    if advanced is not None:
        from formats.advanced_options import apply_advanced_options

        options = apply_advanced_options(options, advanced)

    return options


def build_command_preview(
    url: str,
    selection: FormatSelection,
    output_dir: str,
    filename_template: str,
    advanced: Any | None = None,
) -> str:
    options = build_ytdlp_options(selection, output_dir, filename_template, advanced)

    parts = ["yt-dlp", "-f", shlex.quote(options["format"])]

    if "merge_output_format" in options:
        parts += ["--merge-output-format", options["merge_output_format"]]

    if options.get("writesubtitles"):
        parts.append("--write-subs")
    if options.get("writeautomaticsub"):
        parts.append("--write-auto-subs")
    if options.get("subtitleslangs"):
        parts += ["--sub-langs", ",".join(options["subtitleslangs"])]
    if options.get("writethumbnail"):
        parts.append("--write-thumbnail")

    pp_flag_map = {
        "FFmpegExtractAudio": lambda pp: ["--extract-audio", "--audio-format", pp["preferredcodec"]],
        "FFmpegEmbedSubtitle": lambda pp: ["--embed-subs"],
        "EmbedThumbnail": lambda pp: ["--embed-thumbnail"],
        "FFmpegSplitChapters": lambda pp: ["--split-chapters"],
        "SponsorBlock": lambda pp: ["--sponsorblock-mark" if not _has_modify_chapters(options) else "--sponsorblock-remove", ",".join(sorted(pp["categories"]))],
    }
    seen_keys: set[str] = set()
    for pp in options.get("postprocessors", []):
        key = pp.get("key")
        if key == "FFmpegMetadata":
            if pp.get("add_metadata"):
                parts.append("--add-metadata")
            if pp.get("add_chapters"):
                parts.append("--add-chapters")
            continue
        if key == "ModifyChapters":
            continue  # implied by --sponsorblock-remove above
        if key in pp_flag_map and key not in seen_keys:
            parts += pp_flag_map[key](pp)
            seen_keys.add(key)

    parts += ["-o", shlex.quote(options["outtmpl"])]
    parts.append(shlex.quote(url) if url else '"<URL>"')

    return " ".join(parts)


def _has_modify_chapters(options: dict[str, Any]) -> bool:
    return any(pp.get("key") == "ModifyChapters" for pp in options.get("postprocessors", []))
