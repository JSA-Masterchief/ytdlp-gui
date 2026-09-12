"""The queue's unit of work: everything needed to run, display, and retry
a single download.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.progress import DownloadProgress
from formats.selector import FormatSelection


class DownloadStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    POST_PROCESSING = "post_processing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def display_label(self) -> str:
        return {
            DownloadStatus.QUEUED: "Queued",
            DownloadStatus.DOWNLOADING: "Downloading",
            DownloadStatus.POST_PROCESSING: "Processing",
            DownloadStatus.PAUSED: "Paused",
            DownloadStatus.COMPLETED: "Completed",
            DownloadStatus.FAILED: "Failed",
            DownloadStatus.CANCELLED: "Cancelled",
        }[self]


@dataclass
class DownloadTask:
    url: str
    selection: FormatSelection
    output_dir: str
    filename_template: str
    ytdlp_options: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    title: str | None = None
    status: DownloadStatus = DownloadStatus.QUEUED
    progress: DownloadProgress | None = None
    error_message: str | None = None
    destination_path: str | None = None

    @property
    def is_active(self) -> bool:
        return self.status in (DownloadStatus.DOWNLOADING, DownloadStatus.POST_PROCESSING)

    @property
    def is_finished(self) -> bool:
        return self.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED)

    @property
    def can_retry(self) -> bool:
        return self.status in (DownloadStatus.FAILED, DownloadStatus.CANCELLED, DownloadStatus.PAUSED)

    @property
    def display_title(self) -> str:
        return self.title or self.url
