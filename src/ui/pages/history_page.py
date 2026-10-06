"""The History page: search, filter, and act on past downloads (open
file, open folder, redownload, remove entry).
"""

from __future__ import annotations

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from download.history import HistoryEntry, HistoryStore

_COLUMNS = ["Title", "Date", "Status", "Format", "Actions"]


def _format_timestamp(iso_timestamp: str) -> str:
    # Keep it simple and robust: show date + time up to the minute,
    # without pulling in a timezone-conversion dependency for a label.
    return iso_timestamp.replace("T", " ")[:16]


class HistoryPage(QWidget):
    redownload_requested = Signal(str)  # url

    def __init__(self, store: HistoryStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._visible_entries: list[HistoryEntry] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by title or URL…")
        self.search_edit.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search_edit, stretch=1)

        self.clear_all_button = QPushButton("Clear history")
        self.clear_all_button.clicked.connect(self._on_clear_all)
        toolbar.addWidget(self.clear_all_button)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def refresh(self) -> None:
        query = self.search_edit.text()
        self._visible_entries = self._store.search(query)
        self.table.setRowCount(0)

        for entry in self._visible_entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(entry.title))
            self.table.setItem(row, 1, QTableWidgetItem(_format_timestamp(entry.timestamp)))
            self.table.setItem(row, 2, QTableWidgetItem(entry.status.capitalize()))
            self.table.setItem(row, 3, QTableWidgetItem(entry.format_description or ""))
            self.table.setCellWidget(row, 4, self._build_actions_widget(entry))

    def _build_actions_widget(self, entry: HistoryEntry) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        open_file_button = QPushButton("Open file")
        open_file_button.setObjectName("open_file_button")
        open_file_button.setEnabled(bool(entry.file_path))
        open_file_button.clicked.connect(lambda: self._open_file(entry.file_path))

        open_folder_button = QPushButton("Open folder")
        open_folder_button.setObjectName("open_folder_button")
        open_folder_button.setEnabled(bool(entry.file_path))
        open_folder_button.clicked.connect(lambda: self._open_folder(entry.file_path))

        redownload_button = QPushButton("Redownload")
        redownload_button.setObjectName("redownload_button")
        redownload_button.clicked.connect(lambda: self.redownload_requested.emit(entry.url))

        remove_button = QPushButton("Remove")
        remove_button.setObjectName("remove_button")
        remove_button.clicked.connect(lambda: self._on_remove(entry.id))

        for button in (open_file_button, open_folder_button, redownload_button, remove_button):
            layout.addWidget(button)
        return container

    def _open_file(self, file_path: str | None) -> None:
        if file_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))

    def _open_folder(self, file_path: str | None) -> None:
        if file_path:
            from pathlib import Path

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(file_path).parent)))

    def _on_remove(self, entry_id: str) -> None:
        self._store.remove(entry_id)
        self.refresh()

    def _on_clear_all(self) -> None:
        if self.table.rowCount() == 0:
            return
        confirm = QMessageBox.question(
            self,
            "Clear history",
            "Remove all download history entries? This cannot be undone.",
        )
        if confirm == QMessageBox.Yes:
            self._store.clear()
            self.refresh()
