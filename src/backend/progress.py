"""Translates yt-dlp's raw progress-hook dicts into a clean dataclass.

UI code should depend on DownloadProgress, never on yt-dlp's hook dict
shape directly (its keys/format can change between versions).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class DownloadProgress:
    status: str  # "downloading" | "finished" | "error" | "post_processing"
    filename: str | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None  # combines total_bytes / total_bytes_estimate
    speed_bps: float | None = None  # bytes/sec
    eta_seconds: int | None = None
    percent: float | None = None  # 0-100, derived if not directly given

    @property
    def is_finished(self) -> bool:
        return self.status == "finished"

    @property
    def is_error(self) -> bool:
        return self.status == "error"


def parse_progress_hook(data: dict[str, Any]) -> DownloadProgress:
    """Convert a yt-dlp progress_hooks dict into a DownloadProgress."""
    status = data.get("status", "unknown")

    total = data.get("total_bytes") or data.get("total_bytes_estimate")
    downloaded = data.get("downloaded_bytes")

    percent = None
    if total and downloaded is not None and total > 0:
        percent = round((downloaded / total) * 100, 1)

    return DownloadProgress(
        status=status,
        filename=data.get("filename"),
        downloaded_bytes=downloaded,
        total_bytes=total,
        speed_bps=data.get("speed"),
        eta_seconds=data.get("eta"),
        percent=percent,
    )


ProgressCallback = Callable[[DownloadProgress], None]


def make_yt_dlp_hook(callback: ProgressCallback) -> Callable[[dict], None]:
    """Wrap a DownloadProgress-based callback as a raw yt-dlp progress hook."""

    def _hook(data: dict[str, Any]) -> None:
        callback(parse_progress_hook(data))

    return _hook
