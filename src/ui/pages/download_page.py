"""The primary Download page: paste a link (it's analyzed automatically),
check the video card, pick a preset or exact format, and hit Download."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QPainter, QPalette, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.ytdlp_backend import YtdlpBackend
from download.manager import DownloadManager
from download.task import DownloadTask
from formats.custom_args import merge_custom_args
from formats.parser import available_video_heights
from formats.playlist_selection import apply_archive_option, resolve_selected_entries
from formats.selector import MODE_AUDIO_ONLY, QUALITY_BEST, build_ytdlp_options, render_command_preview
from services.metadata_service import MetadataService
from ui.widgets.advanced_options_widget import AdvancedOptionsWidget
from ui.widgets.common import Card, PageHeader, make_button, make_label, set_role
from ui.widgets.custom_args_widget import CustomArgsWidget
from ui.widgets.format_selector_widget import FormatSelectorWidget
from ui.widgets.metadata_panel import MetadataPanel
from ui.widgets.playlist_table_widget import PlaylistTableWidget
from utils.paths import get_default_download_dir
from utils.validation import validate_urls

logger = logging.getLogger("ytdlp_gui")

MAX_CONTENT_WIDTH = 1040


class UrlInput(QTextEdit):
    """The link box. Grows from one to four lines as links are added;
    Enter analyzes (Shift+Enter adds a line); pasting is plain-text only and
    announces itself so the page can analyze straight away."""

    submitted = Signal()
    pasted = Signal()

    MAX_LINES = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("urlInput")
        self.setAcceptRichText(False)
        self.setAcceptDrops(True)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.document().setDocumentMargin(2)
        self.textChanged.connect(self._fit_height)
        self._fit_height()

    def _fit_height(self) -> None:
        blocks = self.document().blockCount()
        lines = max(1, min(self.MAX_LINES, blocks))
        # Scroll only once there are more links than visible lines.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if blocks > self.MAX_LINES else Qt.ScrollBarAlwaysOff)
        line_height = self.fontMetrics().lineSpacing()
        self.setFixedHeight(int(line_height * lines + 30))

    # Qt draws QTextEdit's placeholder inside the document's width, which is
    # ~0px for an empty NoWrap document, so it never shows. Draw it ourselves.
    def setPlaceholderText(self, text: str) -> None:  # noqa: N802
        self._placeholder = text
        self.viewport().update()

    def placeholderText(self) -> str:  # noqa: N802
        return getattr(self, "_placeholder", "")

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        super().paintEvent(event)
        if self.document().isEmpty() and self.placeholderText():
            painter = QPainter(self.viewport())
            painter.setPen(self.palette().color(QPalette.PlaceholderText))
            margin = int(self.document().documentMargin())
            rect = self.viewport().rect().adjusted(margin, margin, -margin, -margin)
            elided = self.fontMetrics().elidedText(self.placeholderText(), Qt.ElideRight, rect.width())
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignTop, elided)
            painter.end()

    def keyPressEvent(self, event) -> None:  # noqa: N802, ANN001
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                # A real new line (Qt's default Shift+Enter is a soft break
                # that doesn't start a new link line).
                self.textCursor().insertBlock()
                return
            if event.modifiers() & Qt.ControlModifier:
                event.ignore()  # handled by the page's Ctrl+Enter shortcut
                return
            self.submitted.emit()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source) -> None:  # noqa: N802, ANN001
        if source.hasText():
            self.insertPlainText(source.text().strip())
            self.pasted.emit()
        elif source.hasUrls():
            self.insertPlainText("\n".join(url.toString() for url in source.urls()))
            self.pasted.emit()


class DownloadPage(QWidget):
    output_dir_changed = Signal(str)
    task_queued = Signal(str)  # human-readable message
    view_queue_requested = Signal()

    def __init__(
        self,
        metadata_service: MetadataService | None = None,
        download_manager: DownloadManager | None = None,
        initial_output_dir: str | None = None,
        initial_filename_template: str | None = None,
        ffmpeg_location: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._metadata_service = metadata_service or MetadataService(YtdlpBackend())
        self._metadata_service.analysis_finished.connect(self._on_analysis_finished)
        self._metadata_service.analysis_failed.connect(self._on_analysis_failed)
        self._download_manager = download_manager or DownloadManager(YtdlpBackend())
        self._analyzed_title: str | None = None
        self._analyzed_url: str | None = None
        self._analyzed_playlist = None
        self._analyzing = False
        self._initial_output_dir = initial_output_dir
        self._initial_filename_template = initial_filename_template
        self._ffmpeg_location = ffmpeg_location

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self._output_dir = self._initial_output_dir or str(get_default_download_dir())
        self._filename_template = self._initial_filename_template or "%(title)s [%(id)s].%(ext)s"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setObjectName("scrollContent")
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        # Center a width-capped column so wide/ultrawide screens don't
        # stretch the form into hard-to-read lines.
        centering = QHBoxLayout(content)
        centering.setContentsMargins(0, 0, 0, 0)
        column = QWidget()
        column.setMaximumWidth(MAX_CONTENT_WIDTH)
        centering.addStretch(0)
        centering.addWidget(column, stretch=1)
        centering.addStretch(0)

        layout = QVBoxLayout(column)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        layout.addWidget(PageHeader("Download", "Paste a link from YouTube or 1,000+ other sites."))

        layout.addWidget(self._build_url_card())

        self.metadata_panel = MetadataPanel()
        self.metadata_panel.hide()
        layout.addWidget(self.metadata_panel)

        self.playlist_table = PlaylistTableWidget()
        self.playlist_table.selection_changed.connect(self._update_preview)
        self.playlist_table.hide()
        layout.addWidget(self.playlist_table)

        layout.addWidget(self._build_options_card())

        self.advanced_options = AdvancedOptionsWidget()
        self.advanced_options.options_changed.connect(self._update_preview)
        layout.addWidget(self.advanced_options)

        self.custom_args = CustomArgsWidget()
        self.custom_args.args_changed.connect(self._update_preview)
        advanced_layout = self.advanced_options.content.layout()
        advanced_layout.addWidget(self.custom_args)
        advanced_layout.addWidget(self.format_selector.preview_group)

        layout.addStretch(1)

        outer.addWidget(self._build_action_bar())

        # Ctrl+Enter analyzes from anywhere on the page.
        self.analyze_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.analyze_shortcut.activated.connect(self._on_analyze_clicked)
        self.download_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        self.download_shortcut.activated.connect(self._on_download_shortcut)

        self._update_preview()
        self._update_summary()

    def _build_url_card(self) -> Card:
        card = Card()

        row = QHBoxLayout()
        row.setSpacing(8)
        self.url_input = UrlInput()
        self.url_input.setPlaceholderText("Paste a video, playlist or channel link…")
        self.url_input.setAccessibleName("URL input")
        self.url_input.setToolTip("One link per line to queue several at once")
        self.url_input.textChanged.connect(self._update_preview)
        self.url_input.submitted.connect(self._on_analyze_clicked)
        self.url_input.pasted.connect(self._on_link_pasted)
        row.addWidget(self.url_input, stretch=1)

        self.paste_button = make_button("Paste", icon="paste", tooltip="Paste link from clipboard and analyze")
        self.paste_button.clicked.connect(self._on_paste_clicked)
        row.addWidget(self.paste_button, alignment=Qt.AlignTop)

        self.analyze_button = make_button("Analyze", variant="primary", icon="search")
        self.analyze_button.setAccessibleName("Analyze URL")
        self.analyze_button.setToolTip("Fetch video details and available formats (Enter)")
        self.analyze_button.clicked.connect(self._on_analyze_clicked)
        row.addWidget(self.analyze_button, alignment=Qt.AlignTop)
        card.body.addLayout(row)

        self.busy_bar = QProgressBar()
        self.busy_bar.setObjectName("busyBar")
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setTextVisible(False)
        self.busy_bar.hide()
        card.body.addWidget(self.busy_bar)

        self.status_label = make_label("", "error", wrap=True)
        self.status_label.hide()
        card.body.addWidget(self.status_label)

        self.hint_label = make_label(
            "Enter to analyze  ·  Shift+Enter for another link  ·  drag & drop links here", "muted", wrap=True
        )
        card.body.addWidget(self.hint_label)
        return card

    def _build_options_card(self) -> Card:
        card = Card(spacing=14)
        card.body.addWidget(make_label("Format", "sectionTitle"))

        self.format_selector = FormatSelectorWidget()
        self.format_selector.selection_changed.connect(self._update_preview)
        self.format_selector.selection_changed.connect(self._update_summary)
        card.body.addWidget(self.format_selector)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: palette(midlight);")
        card.body.addWidget(divider)

        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        save_col = QVBoxLayout()
        save_col.setSpacing(2)
        save_col.addWidget(make_label("Save to", "fieldLabel"))
        self.output_dir_label = make_label("")
        self.output_dir_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.output_dir_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        save_col.addWidget(self.output_dir_label)
        save_row.addLayout(save_col, stretch=1)

        self.change_dir_button = make_button("Change…", icon="folder", tooltip="Choose where downloads are saved")
        self.change_dir_button.clicked.connect(self._on_change_output_dir)
        save_row.addWidget(self.change_dir_button)
        self.open_dir_button = make_button(variant="icon", icon="open", tooltip="Open download folder")
        self.open_dir_button.clicked.connect(self._open_output_dir)
        save_row.addWidget(self.open_dir_button)
        card.body.addLayout(save_row)
        self._refresh_output_dir_label()
        return card

    def _build_action_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("actionBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(24, 12, 24, 12)
        row.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.summary_label = make_label("", "muted")
        self.summary_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        text_col.addWidget(self.summary_label)
        self.queued_label = make_label("", "success", wrap=True)
        self.queued_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.queued_label.hide()
        text_col.addWidget(self.queued_label)
        row.addLayout(text_col, stretch=1)

        self.view_queue_button = make_button("View queue", variant="ghost", icon="queue")
        self.view_queue_button.clicked.connect(self.view_queue_requested.emit)
        self.view_queue_button.hide()
        row.addWidget(self.view_queue_button)

        self.download_button = make_button("Download", variant="primary", icon="download", size="large")
        self.download_button.setAccessibleName("Start download")
        self.download_button.setToolTip("Analyze a link first")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self._on_download_clicked)
        row.addWidget(self.download_button)
        return bar

    # ------------------------------------------------------------ helpers

    def _refresh_output_dir_label(self) -> None:
        metrics = self.output_dir_label.fontMetrics()
        width = max(200, self.output_dir_label.width() or 420)
        self.output_dir_label.setText(metrics.elidedText(self._output_dir, Qt.ElideMiddle, width))
        self.output_dir_label.setToolTip(self._output_dir)

    def _update_summary(self) -> None:
        sel = self.format_selector.current_selection()
        if sel.mode == MODE_AUDIO_ONLY:
            fmt = "original format" if sel.audio_format == "best" else sel.audio_format.upper()
            text = f"Audio only · {fmt}"
        else:
            quality = "best quality" if sel.quality == QUALITY_BEST else sel.quality
            kind = "Video only" if sel.mode == "video_only" else "Video"
            text = f"{kind} · {quality} · {sel.container.upper()}"
        if self._analyzed_playlist is not None:
            text = f"Playlist · {text}"
        self.summary_label.setText(text)

    def resizeEvent(self, event) -> None:  # noqa: N802, ANN001
        super().resizeEvent(event)
        self._refresh_output_dir_label()

    def _set_busy(self, busy: bool) -> None:
        self._analyzing = busy
        self.busy_bar.setVisible(busy)
        self.analyze_button.setEnabled(not busy)
        self.paste_button.setEnabled(not busy)
        self.analyze_button.setText("Analyzing…" if busy else "Analyze")

    # ------------------------------------------------------------ actions

    def _on_paste_clicked(self) -> None:
        text = QApplication.clipboard().text().strip()
        if not text:
            self.status_label.setText("The clipboard is empty — copy a link first.")
            self.status_label.show()
            return
        self.url_input.setPlainText(text)
        self._on_analyze_clicked()

    def _on_link_pasted(self) -> None:
        valid_urls, _ = validate_urls(self.url_input.toPlainText())
        if valid_urls and not self._analyzing:
            self._on_analyze_clicked()

    def _on_analyze_clicked(self) -> None:
        if self._analyzing:
            return
        raw_text = self.url_input.toPlainText()
        valid_urls, invalid_lines = validate_urls(raw_text)

        if invalid_lines:
            self.status_label.setText(f"Ignored {len(invalid_lines)} line(s) that aren't links.")
            self.status_label.show()
        else:
            self.status_label.hide()

        if not valid_urls:
            self.status_label.setText("That doesn't look like a link. Paste a full URL starting with https://")
            self.status_label.show()
            return

        first_url = valid_urls[0]
        self._set_busy(True)
        self.download_button.setEnabled(False)
        self.queued_label.hide()
        self.view_queue_button.hide()
        self.metadata_panel.show_loading(first_url)
        self.metadata_panel.show()
        self.playlist_table.hide()
        self._analyzed_playlist = None
        self._metadata_service.analyze(first_url)

    def _on_analysis_finished(self, url: str, result) -> None:  # noqa: ANN001
        self._reset_button()
        from backend.models import MediaInfo, PlaylistInfo

        self.metadata_panel.show()
        if isinstance(result, PlaylistInfo):
            self.metadata_panel.show_playlist(result)
            self.playlist_table.load_playlist(result)
            self.playlist_table.show()
            self._analyzed_playlist = result
            self._analyzed_title = result.title
        elif isinstance(result, MediaInfo):
            self.metadata_panel.show_media(result)
            self.format_selector.set_available_heights(available_video_heights(result.formats))
            self.advanced_options.set_available_languages(result.subtitle_languages or result.automatic_caption_languages)
            self.playlist_table.hide()
            self._analyzed_playlist = None
            self._analyzed_title = result.title
        self._analyzed_url = url
        self.download_button.setEnabled(True)
        self.download_button.setToolTip("Add to the download queue (Ctrl+D)")
        self.download_button.setFocus()
        self._update_preview()
        self._update_summary()

    def _on_analysis_failed(self, url: str, user_message: str, technical_detail: str) -> None:
        self._reset_button()
        logger.warning("Analysis failed for %s: %s", url, technical_detail)
        self.metadata_panel.show()
        self.metadata_panel.show_error(user_message)
        self.download_button.setEnabled(False)
        self.download_button.setToolTip("Analyze a link first")

    def _reset_button(self) -> None:
        self._set_busy(False)

    def _on_change_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose download folder", self._output_dir)
        if directory:
            self._output_dir = directory
            self._refresh_output_dir_label()
            self._update_preview()
            self.output_dir_changed.emit(directory)

    def _open_output_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._output_dir))

    def _on_download_shortcut(self) -> None:
        if self.download_button.isEnabled():
            self._on_download_clicked()

    # ------------------------------------------------------------ options

    def _update_preview(self) -> None:
        first_line = self.url_input.toPlainText().strip().splitlines()[:1]
        url = first_line[0].strip() if first_line else ""

        base_options = self._base_options()

        custom_overrides = self.custom_args.current_overrides()
        merged_options, conflicts, overridden_keys = merge_custom_args(base_options, custom_overrides)
        self.custom_args.show_conflicts(conflicts)

        raw_text = self.custom_args.args_edit.text() if self.custom_args.is_valid() else ""
        preview = render_command_preview(url, merged_options, raw_text, overridden_keys)
        self.format_selector.set_preview_text(preview)

    def _base_options(self) -> dict:
        selection = self.format_selector.current_selection()
        advanced = self.advanced_options.current_options()
        options = build_ytdlp_options(selection, self._output_dir, self._filename_template, advanced)
        if self._ffmpeg_location:
            options["ffmpeg_location"] = self._ffmpeg_location
        return options

    def _build_final_options(self, entry_url: str | None = None) -> dict:
        base_options = self._base_options()
        custom_overrides = self.custom_args.current_overrides()
        merged_options, _conflicts, _overridden_keys = merge_custom_args(base_options, custom_overrides)
        return merged_options

    # ----------------------------------------------------------- enqueue

    def _show_queued(self, message: str, ok: bool = True) -> None:
        set_role(self.queued_label, "success" if ok else "error")
        self.queued_label.setText(message)
        self.queued_label.show()
        self.view_queue_button.setVisible(ok)
        if ok:
            self.task_queued.emit(message)

    def _on_download_clicked(self) -> None:
        if not self._analyzed_url:
            return

        if not self.custom_args.is_valid():
            if not self.advanced_options.toggle_button.isChecked():
                self.advanced_options.toggle_button.click()
            self._show_queued("Fix the custom arguments error in Advanced options before downloading.", ok=False)
            return

        if self._analyzed_playlist is not None:
            self._enqueue_playlist_downloads()
        else:
            self._enqueue_single_download()

    def _enqueue_single_download(self) -> None:
        selection = self.format_selector.current_selection()
        options = self._build_final_options()
        task = DownloadTask(
            url=self._analyzed_url,
            selection=selection,
            output_dir=self._output_dir,
            filename_template=self._filename_template,
            ytdlp_options=options,
            title=self._analyzed_title,
        )
        self._download_manager.add_task(task)
        self._show_queued(f"Added to queue: {task.display_title}")

    def _enqueue_playlist_downloads(self) -> None:
        playlist = self._analyzed_playlist
        playlist_options = self.playlist_table.current_options()
        entries = resolve_selected_entries(playlist.entries, playlist_options)

        if not entries:
            self._show_queued("No videos selected.", ok=False)
            return

        selection = self.format_selector.current_selection()
        base_options = self._build_final_options()

        for entry in entries:
            entry_options = apply_archive_option(base_options, playlist_options)
            task = DownloadTask(
                url=entry.url,
                selection=selection,
                output_dir=self._output_dir,
                filename_template=self._filename_template,
                ytdlp_options=entry_options,
                title=entry.title,
            )
            self._download_manager.add_task(task)

        self._show_queued(f"Added {len(entries)} video(s) to queue from '{playlist.title}'.")

    # ------------------------------------------------------------ public

    def apply_settings(
        self,
        output_dir: str,
        filename_template: str,
        ffmpeg_location: str | None = None,
    ) -> None:
        """Called by MainWindow when Settings are saved, so a change to
        the default download directory or filename template takes effect
        immediately without needing to restart the app.
        """
        self._output_dir = output_dir
        self._filename_template = filename_template
        self._ffmpeg_location = ffmpeg_location
        self._refresh_output_dir_label()
        self._update_preview()

    def set_url(self, url: str) -> None:
        """Populate the URL box — used by History's "Redownload" action."""
        self.url_input.setPlainText(url)
