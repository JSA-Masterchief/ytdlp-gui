"""Helpers for turning a raw list[FormatInfo] into GUI-friendly summaries."""

from __future__ import annotations

from backend.models import FormatInfo

STANDARD_HEIGHTS = [2160, 1440, 1080, 720, 480, 360, 240, 144]


def _height_from_resolution(resolution: str | None) -> int | None:
    if not resolution:
        return None
    resolution = resolution.lower()
    if "x" in resolution:
        try:
            return int(resolution.split("x")[-1])
        except ValueError:
            return None
    digits = "".join(ch for ch in resolution.split("p")[0] if ch.isdigit())
    return int(digits) if digits else None


def available_video_heights(formats: list[FormatInfo]) -> list[int]:
    heights: set[int] = set()
    for fmt in formats:
        if fmt.vcodec in (None, "none"):
            continue
        height = _height_from_resolution(fmt.resolution)
        if height:
            heights.add(height)
    return sorted(heights, reverse=True)


def has_audio_only_formats(formats: list[FormatInfo]) -> bool:
    return any(fmt.is_audio_only for fmt in formats)


def format_filesize(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "Unknown size"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def describe_format(fmt: FormatInfo) -> str:
    parts = [fmt.resolution or "audio-only" if fmt.is_audio_only else fmt.resolution or "?"]
    if fmt.fps:
        parts.append(f"{int(fmt.fps)}fps")
    if fmt.dynamic_range and fmt.dynamic_range != "SDR":
        parts.append(fmt.dynamic_range)
    if fmt.vcodec not in (None, "none"):
        parts.append(fmt.vcodec)
    if fmt.acodec not in (None, "none"):
        parts.append(fmt.acodec)
    size = fmt.filesize or fmt.filesize_approx
    parts.append(format_filesize(size))
    return " · ".join(str(p) for p in parts if p)
