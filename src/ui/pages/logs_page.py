"""The Logs page: shows the real application log file (see
utils.logging.configure_logging) with refresh, search, copy, clear, and
save-to-file.

Sensitive data must never reach the log file in the first place — see
utils/logging.py's docstring; this page is just a viewer.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.icons import make_icon
from ui.widgets.common import PageHeader, make_button


class LogsPage(QWidget):
    def __init__(self, log_file_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log_file_path = log_file_path
        self._full_text = ""
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = PageHeader("Logs", "What the app has been doing. Useful when something goes wrong.")
        self.refresh_button = make_button(variant="icon", icon="retry", tooltip="Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        self.copy_button = make_button(variant="icon", icon="copy", tooltip="Copy to clipboard")
        self.copy_button.clicked.connect(self._on_copy)
        self.save_button = make_button(variant="icon", icon="save", tooltip="Save to a file…")
        self.save_button.clicked.connect(self._on_save)
        self.clear_button = make_button("Clear", variant="danger", icon="trash")
        self.clear_button.clicked.connect(self._on_clear)
        for button in (self.refresh_button, self.copy_button, self.save_button, self.clear_button):
            header.actions.addWidget(button)
        layout.addWidget(header)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter log lines…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(make_icon("search", self.palette().placeholderText().color()), QLineEdit.LeadingPosition)
        self.search_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_edit)

        self.text_view = QPlainTextEdit()
        self.text_view.setObjectName("logView")
        self.text_view.setReadOnly(True)
        self.text_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.text_view, stretch=1)

    def refresh(self) -> None:
        try:
            self._full_text = self._log_file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            self._full_text = "(no log file yet)"
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search_edit.text().strip()
        if not query:
            self.text_view.setPlainText(self._full_text)
            return
        matching_lines = [line for line in self._full_text.splitlines() if query.lower() in line.lower()]
        self.text_view.setPlainText("\n".join(matching_lines))

    def _on_copy(self) -> None:
        QApplication.clipboard().setText(self.text_view.toPlainText())

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save log as", "ytdlp-gui.log", "Log files (*.log);;Text files (*.txt);;All files (*)")
        if not path:
            return
        try:
            Path(path).write_text(self.text_view.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Could not save log", f"Failed to save log file: {exc}")

    def _on_clear(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Clear log",
            "Clear the application log file? This cannot be undone.",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._log_file_path.write_text("", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Could not clear log", f"Failed to clear log file: {exc}")
            return
        self.refresh()
