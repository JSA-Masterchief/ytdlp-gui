"""The History page: search, filter, and act on past downloads (open
file, open folder, redownload, remove entry).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QStackedWidget,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from download.history import HistoryEntry, HistoryStore
from ui.icons import make_icon
from ui.theme import current_tokens
from ui.widgets.common import EmptyState, PageHeader, make_button

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
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = PageHeader("History", "Everything you have downloaded. Double-click a row to open the file.")
        self.clear_all_button = make_button("Clear history", variant="danger", icon="trash")
        self.clear_all_button.clicked.connect(self._on_clear_all)
        header.actions.addWidget(self.clear_all_button)
        layout.addWidget(header)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by title or URL…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(make_icon("search", self.palette().placeholderText().color()), QLineEdit.LeadingPosition)
        self.search_edit.textChanged.connect(self.refresh)
        layout.addWidget(self.search_edit)

        self.stack = QStackedWidget()
        self.empty_state = EmptyState("history", "No downloads yet", "Finished downloads are listed here so you can find them again.")
        self.no_results_state = EmptyState("search", "No matches", "Try a different search.")
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.no_results_state)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        header_view = self.table.horizontalHeader()
        header_view.setHighlightSections(False)
        header_view.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 120)
        # The actions column holds 4 icon buttons; size it to its content.
        header_view.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self.stack.addWidget(self.table)
        layout.addWidget(self.stack, stretch=1)

    def refresh(self) -> None:
        query = self.search_edit.text()
        self._visible_entries = self._store.search(query)
        self.table.setRowCount(0)
        tokens = current_tokens()
        for entry in self._visible_entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            title_item = QTableWidgetItem(entry.title)
            title_item.setToolTip(entry.file_path or entry.url)
            self.table.setItem(row, 0, title_item)
            self.table.setItem(row, 1, QTableWidgetItem(_format_timestamp(entry.timestamp)))
            status_item = QTableWidgetItem(entry.status.capitalize())
            color = {"completed": tokens["success"], "failed": tokens["danger"]}.get(entry.status, tokens["muted"])
            status_item.setForeground(QColor(color))
            self.table.setItem(row, 2, status_item)
            self.table.setItem(row, 3, QTableWidgetItem(entry.format_description or ""))
            self.table.setCellWidget(row, 4, self._build_actions_widget(entry))

        if self._visible_entries:
            self.stack.setCurrentWidget(self.table)
        elif query.strip():
            self.stack.setCurrentWidget(self.no_results_state)
        else:
            self.stack.setCurrentWidget(self.empty_state)
        self.clear_all_button.setEnabled(bool(self._visible_entries) or bool(query.strip()))

    def _build_actions_widget(self, entry: HistoryEntry) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 8, 0)
        layout.setSpacing(2)

        has_file = bool(entry.file_path)
        open_file_button = make_button(variant="icon", icon="open", tooltip="Open file" if has_file else "File location unknown")
        open_file_button.setObjectName("open_file_button")
        open_file_button.setEnabled(has_file)
        open_file_button.clicked.connect(lambda: self._open_file(entry.file_path))

        open_folder_button = make_button(variant="icon", icon="folder", tooltip="Show in folder")
        open_folder_button.setObjectName("open_folder_button")
        open_folder_button.setEnabled(has_file)
        open_folder_button.clicked.connect(lambda: self._open_folder(entry.file_path))

        redownload_button = make_button(variant="icon", icon="retry", tooltip="Download again")
        redownload_button.setObjectName("redownload_button")
        redownload_button.clicked.connect(lambda: self.redownload_requested.emit(entry.url))

        remove_button = make_button(variant="icon", icon="trash", tooltip="Remove from history")
        remove_button.setObjectName("remove_button")
        remove_button.clicked.connect(lambda: self._on_remove(entry.id))

        for button in (open_file_button, open_folder_button, redownload_button, remove_button):
            layout.addWidget(button)
        return container

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._visible_entries):
            self._open_file(self._visible_entries[row].file_path)

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
