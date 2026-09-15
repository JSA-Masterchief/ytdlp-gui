"""The primary Download page: paste URL(s), click Analyze, see results.

Downloading itself is Phase 5 (queue). This page's job for Phase 3 is
analysis only — it must never start a download just from Analyze.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.ytdlp_backend import YtdlpBackend
from download.manager import DownloadManager
from download.task import DownloadTask
from formats.parser import available_video_heights
from formats.selector import build_ytdlp_options
from services.metadata_service import MetadataService
from ui.widgets.format_selector_widget import FormatSelectorWidget
from ui.widgets.metadata_panel import MetadataPanel
from utils.paths import get_default_download_dir
from utils.validation import validate_urls

logger = logging.getLogger("ytdlp_gui")


class DownloadPage(QWidget):
    def __init__(
        self,
        metadata_service: MetadataService | None = None,
        download_manager: DownloadManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._metadata_service = metadata_service or MetadataService(YtdlpBackend())
        self._metadata_service.analysis_finished.connect(self._on_analysis_finished)
        self._metadata_service.analysis_failed.connect(self._on_analysis_failed)
        self._download_manager = download_manager or DownloadManager(YtdlpBackend())
        self._analyzed_title: str | None = None
        self._analyzed_url: str | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        self._output_dir = str(get_default_download_dir())
        self._filename_template = "%(title)s [%(id)s].%(ext)s"

        layout = QVBoxLayout(self)

        instructions = QLabel("Paste one or more URLs (one per line):")
        layout.addWidget(instructions)

        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_input.setAcceptDrops(True)
        self.url_input.setFixedHeight(90)
        self.url_input.textChanged.connect(self._update_preview)
        layout.addWidget(self.url_input)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #c0392b;")
        self.status_label.hide()
        layout.addWidget(self.status_label)

        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.clicked.connect(self._on_analyze_clicked)
        layout.addWidget(self.analyze_button, alignment=Qt.AlignLeft)

        self.metadata_panel = MetadataPanel()
        layout.addWidget(self.metadata_panel, stretch=1)

        self.format_selector = FormatSelectorWidget()
        self.format_selector.selection_changed.connect(self._update_preview)
        layout.addWidget(self.format_selector)

        self.download_button = QPushButton("Download")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self._on_download_clicked)
        layout.addWidget(self.download_button, alignment=Qt.AlignLeft)

        self.queued_label = QLabel("")
        self.queued_label.setStyleSheet("color: #2e7d32;")
        self.queued_label.hide()
        layout.addWidget(self.queued_label)

        self._update_preview()

    def _on_analyze_clicked(self) -> None:
        raw_text = self.url_input.toPlainText()
        valid_urls, invalid_lines = validate_urls(raw_text)

        if invalid_lines:
            self.status_label.setText(f"Ignored {len(invalid_lines)} invalid line(s).")
            self.status_label.show()
        else:
            self.status_label.hide()

        if not valid_urls:
            self.status_label.setText("Please paste at least one valid URL.")
            self.status_label.show()
            return

        # Phase 3 analyzes the first URL for display; full multi-URL queueing
        # arrives with the Phase 5 download queue.
        first_url = valid_urls[0]
        self.analyze_button.setEnabled(False)
        self.analyze_button.setText("Analyzing…")
        self.download_button.setEnabled(False)
        self.queued_label.hide()
        self.metadata_panel.clear()
        self._metadata_service.analyze(first_url)

    def _on_analysis_finished(self, url: str, result) -> None:  # noqa: ANN001
        self._reset_button()
        from backend.models import MediaInfo, PlaylistInfo  # local import avoids cycle at module load

        if isinstance(result, PlaylistInfo):
            self.metadata_panel.show_playlist(result)
            self._analyzed_title = result.title
        elif isinstance(result, MediaInfo):
            self.metadata_panel.show_media(result)
            self.format_selector.set_available_heights(available_video_heights(result.formats))
            self._analyzed_title = result.title
        self._analyzed_url = url
        self.download_button.setEnabled(True)
        self._update_preview()

    def _on_analysis_failed(self, url: str, user_message: str, technical_detail: str) -> None:
        self._reset_button()
        logger.warning("Analysis failed for %s: %s", url, technical_detail)
        self.metadata_panel.show_error(user_message)
        self.download_button.setEnabled(False)

    def _reset_button(self) -> None:
        self.analyze_button.setEnabled(True)
        self.analyze_button.setText("Analyze")

    def _update_preview(self) -> None:
        first_line = self.url_input.toPlainText().strip().splitlines()[:1]
        url = first_line[0].strip() if first_line else ""
        self.format_selector.update_preview(url, self._output_dir, self._filename_template)

    def _on_download_clicked(self) -> None:
        if not self._analyzed_url:
            return

        selection = self.format_selector.current_selection()
        options = build_ytdlp_options(selection, self._output_dir, self._filename_template)
        task = DownloadTask(
            url=self._analyzed_url,
            selection=selection,
            output_dir=self._output_dir,
            filename_template=self._filename_template,
            ytdlp_options=options,
            title=self._analyzed_title,
        )
        self._download_manager.add_task(task)

        self.queued_label.setText(f"Added to queue: {task.display_title}")
        self.queued_label.show()
