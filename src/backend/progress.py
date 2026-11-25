"""Translates yt-dlp's raw progress-hook dicts into a clean dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from yt_dlp.utils import DownloadCancelled


@dataclass
class DownloadProgress:
    status: str
    filename: str | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed_bps: float | None = None
    eta_seconds: int | None = None
    percent: float | None = None

    @property
    def is_finished(self) -> bool:
        return self.status == "finished"

    @property
    def is_error(self) -> bool:
        return self.status == "error"


def parse_progress_hook(data: dict[str, Any]) -> DownloadProgress:
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


class DownloadCancelRequested(Exception):
    """Raise this from inside a ProgressCallback to stop an in-progress
    download cooperatively. Translated at the make_yt_dlp_hook boundary
    into yt-dlp's own DownloadCancelled, which is the only exception type
    yt-dlp's internals specifically recognize and cleanly propagate.
    """


def make_yt_dlp_hook(callback: ProgressCallback) -> Callable[[dict], None]:
    def _hook(data: dict[str, Any]) -> None:
        progress = parse_progress_hook(data)
        try:
            callback(progress)
        except DownloadCancelRequested as exc:
            raise DownloadCancelled(str(exc) or "Cancelled by user") from exc

    return _hook
