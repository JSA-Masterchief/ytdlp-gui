"""Shown after analyzing a playlist URL: a per-entry table with
checkboxes, plus the entire-playlist / range / reverse / skip-downloaded
controls from the spec.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.models import PlaylistEntry, PlaylistInfo
from formats.playlist_selection import PlaylistDownloadOptions, PlaylistSelectionMode

_COLUMNS = ["", "#", "Title", "Duration", "Status"]


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return ""
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class PlaylistTableWidget(QWidget):
    selection_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[PlaylistEntry] = []
        self._checkboxes: dict[int, QCheckBox] = {}  # index -> checkbox
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        mode_group = QGroupBox("Which videos?")
        mode_layout = QVBoxLayout(mode_group)

        self.mode_all_radio = QRadioButton("Entire playlist")
        self.mode_all_radio.setChecked(True)
        self.mode_selected_radio = QRadioButton("Selected videos (check boxes below)")
        self.mode_range_radio = QRadioButton("Range")
        mode_layout.addWidget(self.mode_all_radio)
        mode_layout.addWidget(self.mode_selected_radio)

        range_row = QHBoxLayout()
        range_row.addWidget(self.mode_range_radio)
        range_row.addWidget(QLabel("from"))
        self.range_start_spin = QSpinBox()
        self.range_start_spin.setMinimum(1)
        self.range_start_spin.setValue(1)
        range_row.addWidget(self.range_start_spin)
        range_row.addWidget(QLabel("to"))
        self.range_end_spin = QSpinBox()
        self.range_end_spin.setMinimum(1)
        self.range_end_spin.setValue(1)
        range_row.addWidget(self.range_end_spin)
        range_row.addStretch(1)
        mode_layout.addLayout(range_row)

        self.reverse_checkbox = QCheckBox("Reverse order (download last video first)")
        mode_layout.addWidget(self.reverse_checkbox)

        layout.addWidget(mode_group)

        archive_group = QGroupBox("Download archive")
        archive_layout = QHBoxLayout(archive_group)
        self.skip_archived_checkbox = QCheckBox("Skip videos already in archive")
        archive_layout.addWidget(self.skip_archived_checkbox)
        self.archive_path_edit = QLineEdit()
        self.archive_path_edit.setPlaceholderText("Archive file path…")
        self.archive_path_edit.setEnabled(False)
        archive_layout.addWidget(self.archive_path_edit, stretch=1)
        self.archive_browse_button = QPushButton("Browse…")
        self.archive_browse_button.setEnabled(False)
        self.archive_browse_button.clicked.connect(self._on_browse_archive)
        archive_layout.addWidget(self.archive_browse_button)
        layout.addWidget(archive_group)

        select_all_row = QHBoxLayout()
        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.select_none_button = QPushButton("Select none")
        self.select_none_button.clicked.connect(lambda: self._set_all_checked(False))
        select_all_row.addWidget(self.select_all_button)
        select_all_row.addWidget(self.select_none_button)
        select_all_row.addStretch(1)
        layout.addLayout(select_all_row)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def _connect_signals(self) -> None:
        self.mode_all_radio.toggled.connect(self._emit_changed)
        self.mode_selected_radio.toggled.connect(self._emit_changed)
        self.mode_range_radio.toggled.connect(self._emit_changed)
        self.range_start_spin.valueChanged.connect(self._emit_changed)
        self.range_end_spin.valueChanged.connect(self._emit_changed)
        self.reverse_checkbox.toggled.connect(self._emit_changed)
        self.skip_archived_checkbox.toggled.connect(self._on_skip_archived_toggled)
        self.skip_archived_checkbox.toggled.connect(self._emit_changed)
        self.archive_path_edit.textChanged.connect(self._emit_changed)

    def _on_skip_archived_toggled(self, checked: bool) -> None:
        self.archive_path_edit.setEnabled(checked)
        self.archive_browse_button.setEnabled(checked)

    def _on_browse_archive(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Choose archive file", "", "Text files (*.txt);;All files (*)")
        if path:
            self.archive_path_edit.setText(path)

    def _emit_changed(self) -> None:
        self.selection_changed.emit()

    def _set_all_checked(self, checked: bool) -> None:
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(checked)
        self.selection_changed.emit()

    def load_playlist(self, playlist: PlaylistInfo) -> None:
        self._entries = playlist.entries
        self._checkboxes.clear()
        self.table.setRowCount(0)

        max_index = max((e.index for e in playlist.entries if e.index is not None), default=1)
        self.range_start_spin.setMaximum(max_index)
        self.range_end_spin.setMaximum(max_index)
        self.range_end_spin.setValue(max_index)

        for entry in playlist.entries:
            row = self.table.rowCount()
            self.table.insertRow(row)

            checkbox = QCheckBox()
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._emit_changed)
            if entry.index is not None:
                self._checkboxes[entry.index] = checkbox
            self.table.setCellWidget(row, 0, checkbox)

            self.table.setItem(row, 1, QTableWidgetItem(str(entry.index or "")))
            self.table.setItem(row, 2, QTableWidgetItem(entry.title))
            self.table.setItem(row, 3, QTableWidgetItem(_format_duration(entry.duration)))
            self.table.setItem(row, 4, QTableWidgetItem(""))

    def set_entry_status(self, entry_id: str, status_text: str) -> None:
        for row, entry in enumerate(self._entries):
            if entry.id == entry_id:
                item = self.table.item(row, 4)
                if item is not None:
                    item.setText(status_text)
                return

    def current_options(self) -> PlaylistDownloadOptions:
        if self.mode_selected_radio.isChecked():
            mode = PlaylistSelectionMode.SELECTED
        elif self.mode_range_radio.isChecked():
            mode = PlaylistSelectionMode.RANGE
        else:
            mode = PlaylistSelectionMode.ALL

        selected_indices = {index for index, checkbox in self._checkboxes.items() if checkbox.isChecked()}

        return PlaylistDownloadOptions(
            mode=mode,
            selected_indices=selected_indices,
            range_start=self.range_start_spin.value(),
            range_end=self.range_end_spin.value(),
            reverse=self.reverse_checkbox.isChecked(),
            skip_archived=self.skip_archived_checkbox.isChecked(),
            archive_path=self.archive_path_edit.text().strip() or None,
        )
