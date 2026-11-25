"""The Settings page: edits an AppConfig and persists it via
app.config.save_config. Also surfaces FFmpeg detection status so a
missing dependency shows a clear setup message rather than a mysterious
download failure later.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig, save_config
from app.constants import MAX_CONCURRENT_DOWNLOADS_LIMIT, SUPPORTED_THEMES
from backend.ffmpeg_manager import check_ffmpeg, check_ffprobe
from formats.filename_templates import (
    COMMON_TEMPLATE_VARIABLES,
    CUSTOM_PRESET_KEY,
    FILENAME_TEMPLATE_PRESETS,
    find_matching_preset,
    validate_filename_template,
)
from backend import ytdlp_updater
from services.ytdlp_update_service import YtdlpUpdateService
from ui.widgets.common import PageHeader, make_button, set_role


class SettingsPage(QWidget):
    settings_saved = Signal(object)  # AppConfig

    restart_requested = Signal()

    def __init__(
        self,
        config: AppConfig,
        update_service: YtdlpUpdateService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._latest_release = None
        self.update_service = update_service or YtdlpUpdateService(self)
        self._build_ui()
        self._load_into_fields(config)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("scrollContent")
        scroll.setWidget(content)
        outer.addWidget(scroll)

        centering = QHBoxLayout(content)
        centering.setContentsMargins(0, 0, 0, 0)
        column = QWidget()
        column.setMaximumWidth(820)
        centering.addWidget(column, stretch=1)
        centering.addStretch(0)

        layout = QVBoxLayout(column)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(6)
        layout.addWidget(PageHeader("Settings", "Defaults used for every new download."))

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
        browse_button = make_button("Browse…", icon="folder")
        browse_button.clicked.connect(self._on_browse_download_dir)
        dir_row.addWidget(browse_button)
        downloads_form.addRow("Download directory:", dir_row)

        self.max_concurrent_spin = QSpinBox()
        self.max_concurrent_spin.setMinimum(1)
        self.max_concurrent_spin.setMaximum(MAX_CONCURRENT_DOWNLOADS_LIMIT)
        downloads_form.addRow("Max simultaneous downloads:", self.max_concurrent_spin)

        self.template_preset_combo = QComboBox()
        for key, (label, _template) in FILENAME_TEMPLATE_PRESETS.items():
            self.template_preset_combo.addItem(label, userData=key)
        self.template_preset_combo.addItem("Custom", userData=CUSTOM_PRESET_KEY)
        self.template_preset_combo.currentIndexChanged.connect(self._on_template_preset_changed)
        downloads_form.addRow("Filename preset:", self.template_preset_combo)

        variables_help = "\n".join(f"%({name})s  —  {desc}" for name, desc in COMMON_TEMPLATE_VARIABLES.items())
        self.filename_template_edit = QLineEdit()
        self.filename_template_edit.setToolTip("yt-dlp output template. Common variables:\n" + variables_help)
        self.filename_template_edit.setAccessibleName("Filename template")
        self.filename_template_edit.textChanged.connect(self._on_template_text_changed)
        downloads_form.addRow("Filename template:", self.filename_template_edit)

        self.template_status_label = QLabel("")
        self.template_status_label.setWordWrap(True)
        self.template_status_label.hide()
        downloads_form.addRow("", self.template_status_label)

        layout.addWidget(downloads_group)

        tools_group = QGroupBox("FFmpeg")
        tools_form = QFormLayout(tools_group)

        self.ffmpeg_path_edit = QLineEdit()
        self.ffmpeg_path_edit.setPlaceholderText("Leave blank to auto-detect on PATH")
        tools_form.addRow("FFmpeg path:", self.ffmpeg_path_edit)

        self.ffmpeg_status_label = QLabel("")
        # Long install paths (e.g. under WinGet) have no spaces to wrap at;
        # let the label clip instead of widening the whole window. The full
        # path is in the tooltip.
        self.ffmpeg_status_label.setWordWrap(True)
        self.ffmpeg_status_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.ffmpeg_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tools_form.addRow("", self.ffmpeg_status_label)

        refresh_button = make_button("Check again", icon="retry")
        refresh_button.clicked.connect(self._refresh_ffmpeg_status)
        refresh_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        tools_form.addRow("", refresh_button)

        layout.addWidget(tools_group)
        layout.addWidget(self._build_ytdlp_group())

        layout.addSpacing(10)
        save_row = QHBoxLayout()
        self.save_button = make_button("Save settings", variant="primary", icon="check")
        self.save_button.clicked.connect(self._on_save_clicked)
        save_row.addWidget(self.save_button)

        self.saved_label = QLabel("")
        set_role(self.saved_label, "success")
        self.saved_label.hide()
        save_row.addWidget(self.saved_label, stretch=1)
        layout.addLayout(save_row)

        layout.addStretch(1)

        self._refresh_ffmpeg_status()

    # ------------------------------------------------------------ yt-dlp

    def _build_ytdlp_group(self) -> QGroupBox:
        group = QGroupBox("yt-dlp")
        box = QVBoxLayout(group)
        box.setSpacing(10)

        self.ytdlp_version_label = QLabel("")
        self.ytdlp_version_label.setWordWrap(True)
        box.addWidget(self.ytdlp_version_label)

        explainer = QLabel(
            "Sites change often and yt-dlp releases fixes every few weeks. Updating here downloads the "
            "official release from PyPI, checks it, and uses it from the next start, without reinstalling this app."
        )
        explainer.setWordWrap(True)
        explainer.setProperty("role", "muted")
        box.addWidget(explainer)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.check_updates_button = make_button("Check for updates", icon="retry")
        self.check_updates_button.clicked.connect(self._on_check_updates)
        buttons.addWidget(self.check_updates_button)
        self.install_update_button = make_button("Update", variant="primary", icon="download")
        self.install_update_button.clicked.connect(self._on_install_update)
        self.install_update_button.hide()
        buttons.addWidget(self.install_update_button)
        self.restart_button = make_button("Restart now", variant="primary", icon="retry")
        self.restart_button.clicked.connect(self.restart_requested.emit)
        self.restart_button.hide()
        buttons.addWidget(self.restart_button)
        self.reset_ytdlp_button = make_button("Use built-in version", variant="ghost")
        self.reset_ytdlp_button.setToolTip("Forget the downloaded yt-dlp and go back to the one built into the app")
        self.reset_ytdlp_button.clicked.connect(self._on_reset_ytdlp)
        buttons.addWidget(self.reset_ytdlp_button)
        buttons.addStretch(1)
        box.addLayout(buttons)

        self.update_busy_bar = QProgressBar()
        self.update_busy_bar.setObjectName("busyBar")
        self.update_busy_bar.setRange(0, 0)
        self.update_busy_bar.setTextVisible(False)
        self.update_busy_bar.hide()
        box.addWidget(self.update_busy_bar)

        self.update_status_label = QLabel("")
        self.update_status_label.setWordWrap(True)
        self.update_status_label.hide()
        box.addWidget(self.update_status_label)

        self.auto_check_updates_checkbox = QCheckBox("Check for yt-dlp updates when the app starts")
        box.addWidget(self.auto_check_updates_checkbox)

        service = self.update_service
        service.check_finished.connect(self._on_check_finished)
        service.check_failed.connect(self._on_update_failed)
        service.install_finished.connect(self._on_install_finished)
        service.install_failed.connect(self._on_update_failed)
        self._refresh_ytdlp_version()
        return group

    def _refresh_ytdlp_version(self) -> None:
        running = self.update_service.running_version()
        source = "downloaded update" if ytdlp_updater.override_active() else "built in"
        text = f"<b>yt-dlp {running}</b>  ({source})"
        pending = self.update_service.pending_version()
        if pending:
            text += f"<br>Version {pending} is downloaded and will be used after a restart."
        self.ytdlp_version_label.setText(text)
        self.reset_ytdlp_button.setVisible(bool(ytdlp_updater.override_active() or pending))
        self.restart_button.setVisible(bool(pending))

    def _set_update_status(self, text: str, role: str) -> None:
        set_role(self.update_status_label, role)
        self.update_status_label.setText(text)
        self.update_status_label.setVisible(bool(text))

    def _set_update_busy(self, busy: bool) -> None:
        self.update_busy_bar.setVisible(busy)
        self.check_updates_button.setEnabled(not busy)
        self.install_update_button.setEnabled(not busy)

    def _on_check_updates(self) -> None:
        if self.update_service.check():
            self._set_update_busy(True)
            self._set_update_status("Checking PyPI for the latest yt-dlp…", "muted")

    def _on_check_finished(self, release, running: str) -> None:  # noqa: ANN001
        self._set_update_busy(False)
        self._latest_release = release
        if release is None:
            self.install_update_button.hide()
            self._set_update_status(f"You're up to date (yt-dlp {self.update_service.pending_version() or running}).", "success")
        else:
            self.install_update_button.setText(f"Update to {release.version}")
            self.install_update_button.show()
            self._set_update_status(f"yt-dlp {release.version} is available (you have {running}).", "warning")

    def show_available_update(self, release) -> None:  # noqa: ANN001
        """Used by the startup check to pre-fill this section."""
        self._on_check_finished(release, self.update_service.running_version())

    def _on_install_update(self) -> None:
        if self._latest_release is None:
            return
        if self.update_service.install(self._latest_release):
            self._set_update_busy(True)
            self._set_update_status(f"Downloading yt-dlp {self._latest_release.version}…", "muted")

    def _on_install_finished(self, version: str) -> None:
        self._set_update_busy(False)
        self.install_update_button.hide()
        self._latest_release = None
        self._set_update_status(f"yt-dlp {version} is ready. Restart the app to start using it.", "success")
        self._refresh_ytdlp_version()

    def _on_update_failed(self, message: str) -> None:
        self._set_update_busy(False)
        self._set_update_status(message, "error")

    def _on_reset_ytdlp(self) -> None:
        self.update_service.reset_to_bundled()
        self._set_update_status("The built-in yt-dlp will be used after a restart.", "muted")
        self._refresh_ytdlp_version()
        self.restart_button.show()

    # ------------------------------------------------------------ config

    def _load_into_fields(self, config: AppConfig) -> None:
        idx = self.theme_combo.findData(config.theme)
        self.theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.download_dir_edit.setText(config.download_directory)
        self.max_concurrent_spin.setValue(config.max_concurrent_downloads)
        self.filename_template_edit.setText(config.filename_template)
        self.ffmpeg_path_edit.setText(config.ffmpeg_path or "")
        self.auto_check_updates_checkbox.setChecked(config.check_ytdlp_updates)

    def _on_template_preset_changed(self) -> None:
        key = self.template_preset_combo.currentData()
        if key in FILENAME_TEMPLATE_PRESETS:
            # Setting the text re-triggers _on_template_text_changed, which
            # re-selects the same preset — harmless, and keeps one code path.
            self.filename_template_edit.setText(FILENAME_TEMPLATE_PRESETS[key][1])

    def _on_template_text_changed(self, text: str) -> None:
        # Keep the preset dropdown honest about what's typed, without
        # re-firing _on_template_preset_changed (which would overwrite it).
        matching = find_matching_preset(text.strip())
        idx = self.template_preset_combo.findData(matching)
        if idx >= 0 and idx != self.template_preset_combo.currentIndex():
            self.template_preset_combo.blockSignals(True)
            self.template_preset_combo.setCurrentIndex(idx)
            self.template_preset_combo.blockSignals(False)

        result = validate_filename_template(text)
        if not result.ok:
            self.template_status_label.setText(f"⚠ {result.error_message}")
            set_role(self.template_status_label, "error")
            self.template_status_label.show()
        elif result.warning_message:
            self.template_status_label.setText(f"⚠ {result.warning_message}")
            set_role(self.template_status_label, "warning")
            self.template_status_label.show()
        else:
            self.template_status_label.hide()

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
            self.ffmpeg_status_label.setToolTip(ffmpeg_status.path)
            set_role(self.ffmpeg_status_label, "success")
        else:
            self.ffmpeg_status_label.setText(
                "⚠ FFmpeg not found. Some format merges, audio extraction, and subtitle "
                "embedding will not work until it's installed or its path is set above."
            )
            set_role(self.ffmpeg_status_label, "error")
            self.ffmpeg_status_label.setToolTip("")

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
            check_ytdlp_updates=self.auto_check_updates_checkbox.isChecked(),
        )

    def _on_save_clicked(self) -> None:
        template_result = validate_filename_template(self.filename_template_edit.text())
        if not template_result.ok:
            self.saved_label.setText("Fix the filename template before saving.")
            set_role(self.saved_label, "error")
            self.saved_label.show()
            return

        new_config = self.current_config()
        save_config(new_config)
        self._config = new_config
        self.saved_label.setText("Settings saved.")
        set_role(self.saved_label, "success")
        self.saved_label.show()
        self.settings_saved.emit(new_config)
