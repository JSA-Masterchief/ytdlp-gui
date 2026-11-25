"""The format/quality picker: one-click presets for the common cases, the
full Mode/Quality/Container/Audio controls in a responsive grid, and a
read-only command preview that the Download page places under "Advanced"."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
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
from ui.icons import set_button_icon
from ui.widgets.common import ResponsiveGrid, make_label

_MODE_LABELS = {
    MODE_VIDEO_AUDIO: "Video + Audio",
    MODE_VIDEO_ONLY: "Video only",
    MODE_AUDIO_ONLY: "Audio only",
}

_QUALITY_LABELS = [QUALITY_BEST, *QUALITY_HEIGHTS.keys()]

# key -> (chip text, icon, mode, quality, audio format)
PRESETS: dict[str, tuple[str, str, str, str, str]] = {
    "best": ("Best quality", "video", MODE_VIDEO_AUDIO, QUALITY_BEST, "best"),
    "1080p": ("1080p", "video", MODE_VIDEO_AUDIO, "1080p", "best"),
    "720p": ("720p", "video", MODE_VIDEO_AUDIO, "720p", "best"),
    "mp3": ("Audio · MP3", "music", MODE_AUDIO_ONLY, QUALITY_BEST, "mp3"),
}


class FormatSelectorWidget(QWidget):
    selection_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._applying_preset = False
        self._build_ui()
        self._connect_signals()
        self._sync_presets()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        self.preset_buttons: dict[str, QPushButton] = {}
        for key, (text, icon, *_rest) in PRESETS.items():
            chip = QPushButton(text)
            chip.setProperty("variant", "chip")
            chip.setCheckable(True)
            set_button_icon(chip, icon, size=15)
            chip.setToolTip(f"Quick preset: {text}")
            chip.clicked.connect(lambda _checked=False, k=key: self.apply_preset(k))
            self.preset_buttons[key] = chip
            chips_row.addWidget(chip)
        chips_row.addStretch(1)
        layout.addLayout(chips_row)

        self.grid = ResponsiveGrid(min_column_width=150, max_columns=4)

        self.mode_combo = QComboBox()
        for mode_key, label in _MODE_LABELS.items():
            self.mode_combo.addItem(label, userData=mode_key)
        self.mode_combo.setAccessibleName("Download mode")
        self.grid.add_field("Type", self.mode_combo)

        self.quality_combo = QComboBox()
        self.quality_combo.setAccessibleName("Quality")
        self._populate_quality(_QUALITY_LABELS)
        self.quality_field = self.grid.add_field("Quality", self.quality_combo)

        self.container_combo = QComboBox()
        self.container_combo.setAccessibleName("Container")
        for container in VIDEO_CONTAINERS:
            self.container_combo.addItem(container.upper(), userData=container)
        self.container_field = self.grid.add_field("Container", self.container_combo)

        self.audio_format_combo = QComboBox()
        self.audio_format_combo.setAccessibleName("Audio format")
        for fmt in ALL_AUDIO_FORMATS:
            self.audio_format_combo.addItem(fmt.upper() if fmt != "best" else "Best (original)", userData=fmt)
        self.audio_format_combo.setEnabled(False)
        self.audio_field = self.grid.add_field("Audio format", self.audio_format_combo)
        self.grid.set_field_visible(self.audio_field, False)

        layout.addWidget(self.grid)

        # Shown by the Download page inside its "Advanced" section.
        self.preview_group = QWidget()
        preview_layout = QVBoxLayout(self.preview_group)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(4)
        preview_layout.addWidget(make_label("Equivalent yt-dlp command", "fieldLabel"))
        self.preview_box = QPlainTextEdit()
        self.preview_box.setObjectName("commandPreview")
        self.preview_box.setReadOnly(True)
        self.preview_box.setFixedHeight(64)
        self.preview_box.setToolTip(
            "This shows the equivalent yt-dlp command for reference only. "
            "Downloads are run directly through yt-dlp's API, not this text."
        )
        preview_layout.addWidget(self.preview_box)

    def _populate_quality(self, labels: list[str]) -> None:
        self.quality_combo.clear()
        for label in labels:
            display = "Best available" if label == QUALITY_BEST else label
            self.quality_combo.addItem(display, userData=label)

    def _connect_signals(self) -> None:
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        for combo in (self.mode_combo, self.quality_combo, self.container_combo, self.audio_format_combo):
            combo.currentIndexChanged.connect(self._emit_changed)

    def _on_mode_changed(self) -> None:
        mode = self.mode_combo.currentData()
        is_audio_only = mode == MODE_AUDIO_ONLY
        self.container_combo.setEnabled(not is_audio_only)
        self.audio_format_combo.setEnabled(is_audio_only)
        self.quality_combo.setEnabled(not is_audio_only)
        self.grid.set_field_visible(self.container_field, not is_audio_only)
        self.grid.set_field_visible(self.quality_field, not is_audio_only)
        self.grid.set_field_visible(self.audio_field, is_audio_only)

    def _emit_changed(self) -> None:
        if self._applying_preset:
            return
        self._sync_presets()
        self.selection_changed.emit()

    # ---- presets -------------------------------------------------------

    def apply_preset(self, key: str) -> None:
        _text, _icon, mode, quality, audio = PRESETS[key]
        self._applying_preset = True
        try:
            self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(mode)))
            idx = self.quality_combo.findData(quality)
            self.quality_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.audio_format_combo.setCurrentIndex(max(0, self.audio_format_combo.findData(audio)))
        finally:
            self._applying_preset = False
        self._sync_presets()
        self.selection_changed.emit()

    def _matching_preset(self) -> str | None:
        sel = self.current_selection()
        for key, (_t, _i, mode, quality, audio) in PRESETS.items():
            if sel.mode != mode:
                continue
            if mode == MODE_AUDIO_ONLY and sel.audio_format == audio:
                return key
            if mode != MODE_AUDIO_ONLY and sel.quality == quality:
                return key
        return None

    def _sync_presets(self) -> None:
        active = self._matching_preset()
        for key, button in self.preset_buttons.items():
            button.setChecked(key == active)

    # ---- public API ------------------------------------------------------

    def set_available_heights(self, heights: list[int]) -> None:
        available_labels = [QUALITY_BEST]
        for label, height in QUALITY_HEIGHTS.items():
            if height in heights:
                available_labels.append(label)
        previous = self.current_selection().quality
        self._applying_preset = True
        try:
            self._populate_quality(available_labels)
            idx = self.quality_combo.findData(previous)
            self.quality_combo.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self._applying_preset = False
        for key, button in self.preset_buttons.items():
            quality = PRESETS[key][3]
            available = quality == QUALITY_BEST or quality in available_labels
            button.setEnabled(available)
            button.setToolTip(f"Quick preset: {PRESETS[key][0]}" if available else "Not available for this video")
        self._sync_presets()

    def current_selection(self) -> FormatSelection:
        return FormatSelection(
            mode=self.mode_combo.currentData() or MODE_VIDEO_AUDIO,
            quality=self.quality_combo.currentData() or QUALITY_BEST,
            container=self.container_combo.currentData() or "mp4",
            audio_format=self.audio_format_combo.currentData() or "best",
        )

    def update_preview(self, url: str, output_dir: str, filename_template: str, advanced: object | None = None) -> None:
        preview = build_command_preview(url, self.current_selection(), output_dir, filename_template, advanced)
        self.preview_box.setPlainText(preview)

    def set_preview_text(self, text: str) -> None:
        self.preview_box.setPlainText(text)
