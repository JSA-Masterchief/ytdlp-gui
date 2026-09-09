"""The format/quality picker shown after a successful analysis, with a
live, read-only command preview that updates as the user changes options.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from formats.selector import (
    ALL_AUDIO_FORMATS,
    MODE_AUDIO_ONLY,
    MODE_VIDEO_AUDIO,
    MODE_VIDEO_ONLY,
    QUALITY_BEST,
    QUALITY_HEIGHTS,
    VIDEO_CONTAINERS,
    FormatSelection,
    build_command_preview,
)

_MODE_LABELS = {
    MODE_VIDEO_AUDIO: "Video + Audio",
    MODE_VIDEO_ONLY: "Video only",
    MODE_AUDIO_ONLY: "Audio only",
}

_QUALITY_LABELS = [QUALITY_BEST, *QUALITY_HEIGHTS.keys()]


class FormatSelectorWidget(QWidget):
    selection_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        group = QGroupBox("Format")
        form = QFormLayout(group)

        self.mode_combo = QComboBox()
        for mode_key, label in _MODE_LABELS.items():
            self.mode_combo.addItem(label, userData=mode_key)
        form.addRow("Mode:", self.mode_combo)

        self.quality_combo = QComboBox()
        self._populate_quality(_QUALITY_LABELS)
        form.addRow("Quality:", self.quality_combo)

        self.container_combo = QComboBox()
        for container in VIDEO_CONTAINERS:
            self.container_combo.addItem(container.upper(), userData=container)
        form.addRow("Container:", self.container_combo)

        self.audio_format_combo = QComboBox()
        for fmt in ALL_AUDIO_FORMATS:
            self.audio_format_combo.addItem(fmt.upper() if fmt != "best" else "Best", userData=fmt)
        self.audio_format_combo.setEnabled(False)
        form.addRow("Audio format:", self.audio_format_combo)

        layout.addWidget(group)

        preview_group = QGroupBox("Command Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_box = QPlainTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setFixedHeight(60)
        self.preview_box.setToolTip(
            "This shows the equivalent yt-dlp command for reference only. "
            "Downloads are run directly through yt-dlp's API, not this text."
        )
        preview_layout.addWidget(self.preview_box)
        layout.addWidget(preview_group)

    def _populate_quality(self, labels: list[str]) -> None:
        self.quality_combo.clear()
        for label in labels:
            display = "Best available" if label == QUALITY_BEST else label
            self.quality_combo.addItem(display, userData=label)

    def _connect_signals(self) -> None:
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.mode_combo.currentIndexChanged.connect(self._emit_changed)
        self.quality_combo.currentIndexChanged.connect(self._emit_changed)
        self.container_combo.currentIndexChanged.connect(self._emit_changed)
        self.audio_format_combo.currentIndexChanged.connect(self._emit_changed)

    def _on_mode_changed(self) -> None:
        mode = self.mode_combo.currentData()
        is_audio_only = mode == MODE_AUDIO_ONLY
        self.container_combo.setEnabled(not is_audio_only)
        self.audio_format_combo.setEnabled(is_audio_only)

    def _emit_changed(self) -> None:
        self.selection_changed.emit()

    def set_available_heights(self, heights: list[int]) -> None:
        """Restrict the quality dropdown to resolutions actually available
        for the analyzed video, keeping "Best available" always present.
        """
        available_labels = [QUALITY_BEST]
        for label, height in QUALITY_HEIGHTS.items():
            if height in heights:
                available_labels.append(label)
        previous = self.current_selection().quality
        self._populate_quality(available_labels)
        # Restore the previous choice if it's still valid, else fall back to best.
        idx = self.quality_combo.findData(previous)
        self.quality_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def current_selection(self) -> FormatSelection:
        return FormatSelection(
            mode=self.mode_combo.currentData() or MODE_VIDEO_AUDIO,
            quality=self.quality_combo.currentData() or QUALITY_BEST,
            container=self.container_combo.currentData() or "mp4",
            audio_format=self.audio_format_combo.currentData() or "best",
        )

    def update_preview(self, url: str, output_dir: str, filename_template: str) -> None:
        preview = build_command_preview(url, self.current_selection(), output_dir, filename_template)
        self.preview_box.setPlainText(preview)
