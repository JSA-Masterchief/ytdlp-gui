"""Displays MediaInfo/PlaylistInfo after a successful analysis.

Kept as its own widget (rather than inline in DownloadPage) so it can be
reused later if a "re-analyze" or history-detail view needs the same
display logic.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from backend.models import MediaInfo, PlaylistInfo


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "Unknown length"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_view_count(count: int | None) -> str:
    if count is None:
        return ""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M views"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K views"
    return f"{count} views"


class MetadataPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 600;")

        self.subtitle_label = QLabel()
        self.subtitle_label.setStyleSheet("color: gray;")

        self.detail_label = QLabel()
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        layout.addWidget(self.detail_label)
        layout.addStretch(1)

        self.clear()

    def clear(self) -> None:
        self.title_label.setText("")
        self.subtitle_label.setText("Paste a URL and click Analyze to see details here.")
        self.detail_label.setText("")

    def show_error(self, message: str) -> None:
        self.title_label.setText("Analysis failed")
        self.subtitle_label.setText("")
        self.detail_label.setText(message)

    def show_media(self, info: MediaInfo) -> None:
        self.title_label.setText(info.title)

        parts = []
        if info.uploader:
            parts.append(info.uploader)
        parts.append(_format_duration(info.duration))
        view_text = _format_view_count(info.view_count)
        if view_text:
            parts.append(view_text)
        self.subtitle_label.setText(" · ".join(parts))

        detail_lines = [f"Source: {info.extractor}"]
        if info.upload_date:
            detail_lines.append(f"Uploaded: {info.upload_date}")
        detail_lines.append(f"Formats available: {len(info.formats)}")
        if info.subtitle_languages:
            detail_lines.append(f"Subtitles: {', '.join(info.subtitle_languages)}")
        self.detail_label.setText("\n".join(detail_lines))

    def show_playlist(self, info: PlaylistInfo) -> None:
        self.title_label.setText(info.title)
        subtitle = info.uploader or ""
        self.subtitle_label.setText(subtitle)
        self.detail_label.setText(f"Playlist with {info.entry_count} video(s)")
