"""Maps simple GUI choices (mode/quality/container/audio format) to real
yt-dlp format-selector syntax and YoutubeDL options dicts.

This is the one place that should know what a yt-dlp format string looks
like — UI code just builds a FormatSelection and hands it here.
"""

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
# Ordered highest to lowest for display purposes.
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

# Best-guess matching audio container per video container, used so the
# audio stream muxes cleanly without a re-encode in the common case.
_CONTAINER_AUDIO_EXT = {"mp4": "m4a", "webm": "webm", "mkv": "m4a"}


@dataclass
class FormatSelection:
    mode: str = MODE_VIDEO_AUDIO
    quality: str = QUALITY_BEST  # "best" or a key of QUALITY_HEIGHTS
    container: str = "mp4"
    audio_format: str = AUDIO_FORMAT_BEST
    custom_format_string: str | None = None  # advanced override, takes precedence

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
    """Build the yt-dlp `-f` selector string for this selection."""
    if selection.custom_format_string:
        return selection.custom_format_string

    height = _height_filter(selection.quality)

    if selection.mode == MODE_AUDIO_ONLY:
        return "ba/b"

    if selection.mode == MODE_VIDEO_ONLY:
        return f"bv*{height}/wv*{height}"

    # MODE_VIDEO_AUDIO
    if selection.container in VIDEO_CONTAINERS:
        audio_ext = _CONTAINER_AUDIO_EXT.get(selection.container, "m4a")
        return f"bv*{height}[ext={selection.container}]+ba[ext={audio_ext}]/b{height}[ext={selection.container}]/b{height}"

    return f"bv*{height}+ba/b{height}"


def build_ytdlp_options(
    selection: FormatSelection,
    output_dir: str,
    filename_template: str,
) -> dict[str, Any]:
    """Build the options dict to hand to YtdlpBackend.download()."""
    options: dict[str, Any] = {
        "format": build_format_string(selection),
        "outtmpl": str(Path(output_dir) / filename_template),
    }

    if selection.mode == MODE_AUDIO_ONLY and selection.audio_format != AUDIO_FORMAT_BEST:
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": selection.audio_format,
                "preferredquality": "0",  # best available
            }
        ]
    elif selection.mode == MODE_VIDEO_AUDIO and selection.container in VIDEO_CONTAINERS:
        options["merge_output_format"] = selection.container

    return options


def build_command_preview(url: str, selection: FormatSelection, output_dir: str, filename_template: str) -> str:
    """Build a read-only, display-only approximation of the equivalent CLI
    command. This is NEVER parsed back or executed — actual downloads run
    through YtdlpBackend.download() with an argument dict, not a shell
    string. Quoting here is for legibility only.
    """
    options = build_ytdlp_options(selection, output_dir, filename_template)

    parts = ["yt-dlp", "-f", shlex.quote(options["format"])]

    if "merge_output_format" in options:
        parts += ["--merge-output-format", options["merge_output_format"]]

    for pp in options.get("postprocessors", []):
        if pp.get("key") == "FFmpegExtractAudio":
            parts += ["--extract-audio", "--audio-format", pp["preferredcodec"]]

    parts += ["-o", shlex.quote(options["outtmpl"])]
    parts.append(shlex.quote(url) if url else '"<URL>"')

    return " ".join(parts)
