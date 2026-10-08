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
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LogsPage(QWidget):
    def __init__(self, log_file_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log_file_path = log_file_path
        self._full_text = ""
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search log…")
        self.search_edit.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.search_edit, stretch=1)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_button)

        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self._on_copy)
        toolbar.addWidget(self.copy_button)

        self.save_button = QPushButton("Save…")
        self.save_button.clicked.connect(self._on_save)
        toolbar.addWidget(self.save_button)

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._on_clear)
        toolbar.addWidget(self.clear_button)

        layout.addLayout(toolbar)

        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.text_view)

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
