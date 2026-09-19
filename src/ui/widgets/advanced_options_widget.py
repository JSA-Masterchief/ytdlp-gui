"""Collapsible panel for subtitle, SponsorBlock, chapter, and
metadata/thumbnail options. Hidden behind a toggle so the basic Download
page stays simple by default, per the "don't overwhelm new users" goal.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from formats.advanced_options import (
    SPONSORBLOCK_ACTION_MARK,
    SPONSORBLOCK_ACTION_REMOVE,
    SPONSORBLOCK_CATEGORIES,
    SUBTITLE_MODE_ALL,
    SUBTITLE_MODE_AUTO,
    SUBTITLE_MODE_MANUAL,
    SUBTITLE_MODE_NONE,
    AdvancedOptions,
    ChapterOptions,
    MetadataOptions,
    SponsorBlockOptions,
    SubtitleOptions,
)

_SUBTITLE_MODE_LABELS = {
    SUBTITLE_MODE_NONE: "No subtitles",
    SUBTITLE_MODE_MANUAL: "Manual subtitles",
    SUBTITLE_MODE_AUTO: "Auto-generated subtitles",
    SUBTITLE_MODE_ALL: "All available subtitles",
}


class AdvancedOptionsWidget(QWidget):
    options_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.toggle_button = QToolButton()
        self.toggle_button.setText("Advanced options")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.RightArrow)
        self.toggle_button.clicked.connect(self._on_toggle)
        outer.addWidget(self.toggle_button)

        self.content = QWidget()
        self.content.setVisible(False)
        content_layout = QVBoxLayout(self.content)

        content_layout.addWidget(self._build_subtitles_group())
        content_layout.addWidget(self._build_sponsorblock_group())
        content_layout.addWidget(self._build_chapters_metadata_group())

        outer.addWidget(self.content)

    def _build_subtitles_group(self) -> QGroupBox:
        group = QGroupBox("Subtitles")
        form = QFormLayout(group)

        self.subtitle_mode_combo = QComboBox()
        for mode, label in _SUBTITLE_MODE_LABELS.items():
            self.subtitle_mode_combo.addItem(label, userData=mode)
        form.addRow("Include:", self.subtitle_mode_combo)

        self.subtitle_languages_edit = QLineEdit("en")
        self.subtitle_languages_edit.setToolTip(
            "Comma-separated language codes (e.g. en,es,fr), or 'all' for every available language."
        )
        form.addRow("Languages:", self.subtitle_languages_edit)

        self.subtitle_embed_checkbox = QCheckBox("Embed in video file (requires FFmpeg)")
        form.addRow("", self.subtitle_embed_checkbox)

        return group

    def _build_sponsorblock_group(self) -> QGroupBox:
        group = QGroupBox("SponsorBlock")
        layout = QVBoxLayout(group)

        self.sponsorblock_enabled_checkbox = QCheckBox("Use SponsorBlock")
        layout.addWidget(self.sponsorblock_enabled_checkbox)

        action_row = QHBoxLayout()
        self.sponsorblock_action_combo = QComboBox()
        self.sponsorblock_action_combo.addItem("Remove segments", userData=SPONSORBLOCK_ACTION_REMOVE)
        self.sponsorblock_action_combo.addItem("Mark segments as chapters", userData=SPONSORBLOCK_ACTION_MARK)
        self.sponsorblock_action_combo.setEnabled(False)
        action_row.addWidget(self.sponsorblock_action_combo)
        layout.addLayout(action_row)

        self._sponsorblock_category_checkboxes: dict[str, QCheckBox] = {}
        categories_row = QHBoxLayout()
        for code, label in SPONSORBLOCK_CATEGORIES.items():
            checkbox = QCheckBox(label)
            checkbox.setEnabled(False)
            checkbox.setChecked(code == "sponsor")
            self._sponsorblock_category_checkboxes[code] = checkbox
            categories_row.addWidget(checkbox)
        layout.addLayout(categories_row)

        return group

    def _build_chapters_metadata_group(self) -> QGroupBox:
        group = QGroupBox("Chapters && Metadata")
        layout = QVBoxLayout(group)

        self.embed_chapters_checkbox = QCheckBox("Embed chapters")
        self.split_chapters_checkbox = QCheckBox("Split into separate files by chapter")
        self.embed_metadata_checkbox = QCheckBox("Embed metadata (title, uploader, etc.)")
        self.embed_thumbnail_checkbox = QCheckBox("Embed thumbnail")
        self.write_thumbnail_checkbox = QCheckBox("Save thumbnail as a separate file")

        for checkbox in (
            self.embed_chapters_checkbox,
            self.split_chapters_checkbox,
            self.embed_metadata_checkbox,
            self.embed_thumbnail_checkbox,
            self.write_thumbnail_checkbox,
        ):
            layout.addWidget(checkbox)

        return group

    def _connect_signals(self) -> None:
        self.subtitle_mode_combo.currentIndexChanged.connect(self._on_subtitle_mode_changed)
        self.subtitle_mode_combo.currentIndexChanged.connect(self._emit_changed)
        self.subtitle_languages_edit.textChanged.connect(self._emit_changed)
        self.subtitle_embed_checkbox.toggled.connect(self._emit_changed)

        self.sponsorblock_enabled_checkbox.toggled.connect(self._on_sponsorblock_toggled)
        self.sponsorblock_enabled_checkbox.toggled.connect(self._emit_changed)
        self.sponsorblock_action_combo.currentIndexChanged.connect(self._emit_changed)
        for checkbox in self._sponsorblock_category_checkboxes.values():
            checkbox.toggled.connect(self._emit_changed)

        self.embed_chapters_checkbox.toggled.connect(self._emit_changed)
        self.split_chapters_checkbox.toggled.connect(self._emit_changed)
        self.embed_metadata_checkbox.toggled.connect(self._emit_changed)
        self.embed_thumbnail_checkbox.toggled.connect(self._emit_changed)
        self.write_thumbnail_checkbox.toggled.connect(self._emit_changed)

        # Apply the initial enabled/disabled state now that handlers are
        # connected — the combo already had its items (and thus a current
        # index) set during _build_ui, before this signal existed to react
        # to it, so nothing would otherwise disable the dependent controls
        # for the default "No subtitles" selection.
        self._on_subtitle_mode_changed()

    def _on_toggle(self) -> None:
        expanded = self.toggle_button.isChecked()
        self.content.setVisible(expanded)
        self.toggle_button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def _on_subtitle_mode_changed(self) -> None:
        enabled = self.subtitle_mode_combo.currentData() != SUBTITLE_MODE_NONE
        self.subtitle_languages_edit.setEnabled(enabled)
        self.subtitle_embed_checkbox.setEnabled(enabled)

    def _on_sponsorblock_toggled(self, checked: bool) -> None:
        self.sponsorblock_action_combo.setEnabled(checked)
        for checkbox in self._sponsorblock_category_checkboxes.values():
            checkbox.setEnabled(checked)

    def _emit_changed(self) -> None:
        self.options_changed.emit()

    def _parse_languages(self) -> list[str]:
        raw = self.subtitle_languages_edit.text().strip()
        if not raw:
            return ["en"]
        return [lang.strip() for lang in raw.split(",") if lang.strip()]

    def current_options(self) -> AdvancedOptions:
        selected_categories = [
            code for code, checkbox in self._sponsorblock_category_checkboxes.items() if checkbox.isChecked()
        ]
        return AdvancedOptions(
            subtitles=SubtitleOptions(
                mode=self.subtitle_mode_combo.currentData() or SUBTITLE_MODE_NONE,
                languages=self._parse_languages(),
                embed=self.subtitle_embed_checkbox.isChecked(),
            ),
            sponsorblock=SponsorBlockOptions(
                enabled=self.sponsorblock_enabled_checkbox.isChecked(),
                action=self.sponsorblock_action_combo.currentData() or SPONSORBLOCK_ACTION_REMOVE,
                categories=selected_categories or ["sponsor"],
            ),
            chapters=ChapterOptions(
                embed_chapters=self.embed_chapters_checkbox.isChecked(),
                split_chapters=self.split_chapters_checkbox.isChecked(),
            ),
            metadata=MetadataOptions(
                embed_metadata=self.embed_metadata_checkbox.isChecked(),
                embed_thumbnail=self.embed_thumbnail_checkbox.isChecked(),
                write_thumbnail=self.write_thumbnail_checkbox.isChecked(),
            ),
        )

    def set_available_languages(self, languages: list[str]) -> None:
        """Optional: called after analysis to prefill the languages field
        with what's actually available, if the user hasn't typed anything.
        """
        if not self.subtitle_languages_edit.text().strip() and languages:
            self.subtitle_languages_edit.setText(languages[0])
