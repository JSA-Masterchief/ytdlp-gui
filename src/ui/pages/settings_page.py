"""The Settings page: edits an AppConfig and persists it via
app.config.save_config. Also surfaces FFmpeg detection status so a
missing dependency shows a clear setup message rather than a mysterious
download failure later.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig, save_config
from app.constants import MAX_CONCURRENT_DOWNLOADS_LIMIT, SUPPORTED_THEMES
from backend.ffmpeg_manager import check_ffmpeg, check_ffprobe


class SettingsPage(QWidget):
    settings_saved = Signal(object)  # AppConfig

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._build_ui()
        self._load_into_fields(config)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        general_group = QGroupBox("General")
        general_form = QFormLayout(general_group)

        self.theme_combo = QComboBox()
        for theme in SUPPORTED_THEMES:
            self.theme_combo.addItem(theme.capitalize(), userData=theme)
        general_form.addRow("Theme:", self.theme_combo)

        layout.addWidget(general_group)

        downloads_group = QGroupBox("Downloads")
        downloads_form = QFormLayout(downloads_group)

        dir_row = QHBoxLayout()
        self.download_dir_edit = QLineEdit()
        dir_row.addWidget(self.download_dir_edit, stretch=1)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._on_browse_download_dir)
        dir_row.addWidget(browse_button)
        downloads_form.addRow("Download directory:", dir_row)

        self.max_concurrent_spin = QSpinBox()
        self.max_concurrent_spin.setMinimum(1)
        self.max_concurrent_spin.setMaximum(MAX_CONCURRENT_DOWNLOADS_LIMIT)
        downloads_form.addRow("Max simultaneous downloads:", self.max_concurrent_spin)

        self.filename_template_edit = QLineEdit()
        self.filename_template_edit.setToolTip("yt-dlp output template, e.g. %(title)s [%(id)s].%(ext)s")
        downloads_form.addRow("Filename template:", self.filename_template_edit)

        layout.addWidget(downloads_group)

        tools_group = QGroupBox("yt-dlp && FFmpeg")
        tools_form = QFormLayout(tools_group)

        self.ffmpeg_path_edit = QLineEdit()
        self.ffmpeg_path_edit.setPlaceholderText("Leave blank to auto-detect on PATH")
        tools_form.addRow("FFmpeg path:", self.ffmpeg_path_edit)

        self.ffmpeg_status_label = QLabel("")
        tools_form.addRow("", self.ffmpeg_status_label)

        refresh_button = QPushButton("Check FFmpeg")
        refresh_button.clicked.connect(self._refresh_ffmpeg_status)
        tools_form.addRow("", refresh_button)

        layout.addWidget(tools_group)

        self.save_button = QPushButton("Save settings")
        self.save_button.clicked.connect(self._on_save_clicked)
        layout.addWidget(self.save_button)

        self.saved_label = QLabel("")
        self.saved_label.setStyleSheet("color: #2e7d32;")
        self.saved_label.hide()
        layout.addWidget(self.saved_label)

        layout.addStretch(1)

        self._refresh_ffmpeg_status()

    def _load_into_fields(self, config: AppConfig) -> None:
        idx = self.theme_combo.findData(config.theme)
        self.theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.download_dir_edit.setText(config.download_directory)
        self.max_concurrent_spin.setValue(config.max_concurrent_downloads)
        self.filename_template_edit.setText(config.filename_template)
        self.ffmpeg_path_edit.setText(config.ffmpeg_path or "")

    def _on_browse_download_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose download directory", self.download_dir_edit.text())
        if directory:
            self.download_dir_edit.setText(directory)

    def _refresh_ffmpeg_status(self) -> None:
        configured = self.ffmpeg_path_edit.text().strip() or None
        ffmpeg_status = check_ffmpeg(configured)
        check_ffprobe(configured)  # checked together; ffmpeg status covers the common case for display

        if ffmpeg_status.found:
            self.ffmpeg_status_label.setText(f"✓ Found at {ffmpeg_status.path}")
            self.ffmpeg_status_label.setStyleSheet("color: #2e7d32;")
        else:
            self.ffmpeg_status_label.setText(
                "⚠ FFmpeg not found. Some format merges, audio extraction, and subtitle "
                "embedding will not work until it's installed or its path is set above."
            )
            self.ffmpeg_status_label.setStyleSheet("color: #c0392b;")

    def current_config(self) -> AppConfig:
        return AppConfig(
            schema_version=self._config.schema_version,
            theme=self.theme_combo.currentData() or "system",
            download_directory=self.download_dir_edit.text().strip() or self._config.download_directory,
            max_concurrent_downloads=self.max_concurrent_spin.value(),
            ytdlp_path=self._config.ytdlp_path,
            ffmpeg_path=self.ffmpeg_path_edit.text().strip() or None,
            ffprobe_path=self._config.ffprobe_path,
            filename_template=self.filename_template_edit.text().strip() or self._config.filename_template,
        )

    def _on_save_clicked(self) -> None:
        new_config = self.current_config()
        save_config(new_config)
        self._config = new_config
        self.saved_label.setText("Settings saved.")
        self.saved_label.show()
        self.settings_saved.emit(new_config)
