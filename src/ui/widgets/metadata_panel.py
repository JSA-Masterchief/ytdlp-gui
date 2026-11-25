"""Displays MediaInfo/PlaylistInfo after a successful analysis, as a card
with the video's thumbnail (fetched in the background) beside its details."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from backend.models import MediaInfo, PlaylistInfo
from ui.widgets.common import Card, make_label, set_role

THUMB_SIZE = QSize(192, 108)
THUMB_SIZE_COMPACT = QSize(128, 72)


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


def _format_upload_date(raw: str | None) -> str:
    if not raw or len(raw) != 8 or not raw.isdigit():
        return raw or ""
    return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"


def _rounded(pixmap: QPixmap, size: QSize, radius: float = 8.0) -> QPixmap:
    scaled = pixmap.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = (scaled.width() - size.width()) // 2
    y = (scaled.height() - size.height()) // 2
    scaled = scaled.copy(x, y, size.width(), size.height())
    result = QPixmap(size)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return result


class MetadataPanel(Card):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, margins=14)
        self._network: QNetworkAccessManager | None = None
        self._pending_reply: QNetworkReply | None = None
        self._thumb_source: QPixmap | None = None

        row = QHBoxLayout()
        row.setSpacing(16)
        self.body.addLayout(row)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setObjectName("thumbnail")
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setFixedSize(THUMB_SIZE)
        row.addWidget(self.thumbnail_label, alignment=Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        self.title_label = make_label("", "mediaTitle", wrap=True)
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.subtitle_label = make_label("", "muted", wrap=True)
        self.detail_label = make_label("", "muted", wrap=True)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.subtitle_label)
        text_col.addSpacing(4)
        text_col.addWidget(self.detail_label)
        text_col.addStretch(1)
        row.addLayout(text_col, stretch=1)

        self.clear()

    # ---- states ------------------------------------------------------------

    def clear(self) -> None:
        self._cancel_thumbnail()
        set_role(self.title_label, "mediaTitle")
        self.title_label.setText("")
        self.subtitle_label.setText("Paste a URL and click Analyze to see details here.")
        self.detail_label.setText("")
        self.thumbnail_label.hide()

    def show_loading(self, url: str) -> None:
        self.clear()
        self.title_label.setText("Fetching video details…")
        self.subtitle_label.setText(url)
        self._show_placeholder_thumb("…")

    def show_error(self, message: str) -> None:
        self._cancel_thumbnail()
        set_role(self.title_label, "error")
        self.title_label.setText("Analysis failed")
        self.subtitle_label.setText("")
        self.detail_label.setText(message)
        self.thumbnail_label.hide()

    def show_media(self, info: MediaInfo) -> None:
        set_role(self.title_label, "mediaTitle")
        self.title_label.setText(info.title)

        parts = []
        if info.uploader:
            parts.append(info.uploader)
        parts.append(_format_duration(info.duration))
        view_text = _format_view_count(info.view_count)
        if view_text:
            parts.append(view_text)
        self.subtitle_label.setText(" · ".join(parts))

        details = [f"Source: {info.extractor}"]
        if info.upload_date:
            details.append(f"Uploaded {_format_upload_date(info.upload_date)}")
        details.append(f"{len(info.formats)} formats")
        if info.subtitle_languages:
            langs = info.subtitle_languages
            shown = ", ".join(langs[:6]) + (f" +{len(langs) - 6} more" if len(langs) > 6 else "")
            details.append(f"Subtitles: {shown}")
        self.detail_label.setText("   ·   ".join(details))
        self._load_thumbnail(getattr(info, "thumbnail_url", None))

    def show_playlist(self, info: PlaylistInfo) -> None:
        set_role(self.title_label, "mediaTitle")
        self.title_label.setText(info.title)
        self.subtitle_label.setText(info.uploader or "")
        self.detail_label.setText(f"Playlist with {info.entry_count} video(s)")
        self._cancel_thumbnail()
        self._show_placeholder_thumb(f"{info.entry_count}\nvideos")

    # ---- thumbnail -----------------------------------------------------------

    def _thumb_size(self) -> QSize:
        return THUMB_SIZE_COMPACT if self.width() and self.width() < 560 else THUMB_SIZE

    def _show_placeholder_thumb(self, text: str) -> None:
        self.thumbnail_label.setPixmap(QPixmap())
        self.thumbnail_label.setText(text)
        self.thumbnail_label.setFixedSize(self._thumb_size())
        self.thumbnail_label.show()

    def _cancel_thumbnail(self) -> None:
        self._thumb_source = None
        if self._pending_reply is not None:
            reply, self._pending_reply = self._pending_reply, None
            reply.abort()
            reply.deleteLater()

    def _load_thumbnail(self, url: str | None) -> None:
        self._cancel_thumbnail()
        if not url or not url.startswith(("http://", "https://")):
            self.thumbnail_label.hide()
            return
        self._show_placeholder_thumb("")
        if self._network is None:
            self._network = QNetworkAccessManager(self)
        request = QNetworkRequest(QUrl(url))
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)
        request.setTransferTimeout(10_000)
        reply = self._network.get(request)
        self._pending_reply = reply
        reply.finished.connect(lambda r=reply: self._on_thumbnail_finished(r))

    def _on_thumbnail_finished(self, reply: QNetworkReply) -> None:
        if reply is not self._pending_reply:
            reply.deleteLater()
            return
        self._pending_reply = None
        pixmap = QPixmap()
        if reply.error() == QNetworkReply.NoError and pixmap.loadFromData(reply.readAll()):
            self._thumb_source = pixmap
            self._apply_thumbnail()
        else:
            self.thumbnail_label.hide()
        reply.deleteLater()

    def _apply_thumbnail(self) -> None:
        if self._thumb_source is None:
            return
        size = self._thumb_size()
        self.thumbnail_label.setFixedSize(size)
        self.thumbnail_label.setText("")
        self.thumbnail_label.setPixmap(_rounded(self._thumb_source, size))
        self.thumbnail_label.show()

    def resizeEvent(self, event) -> None:  # noqa: N802, ANN001
        super().resizeEvent(event)
        if self.thumbnail_label.isVisible() and self.thumbnail_label.size() != self._thumb_size():
            if self._thumb_source is not None:
                self._apply_thumbnail()
            else:
                self.thumbnail_label.setFixedSize(self._thumb_size())
