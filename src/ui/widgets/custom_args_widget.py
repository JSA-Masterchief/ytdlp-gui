"""The raw "Custom yt-dlp Arguments" box: validates live against yt-dlp's
own parser, and surfaces conflicts with GUI controls without silently
overriding anything.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from formats.custom_args import CustomArgsResult, parse_custom_args


class CustomArgsWidget(QWidget):
    args_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_result = CustomArgsResult(ok=True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("Custom yt-dlp arguments")
        group_layout = QVBoxLayout(group)

        hint = QLabel(
            "Real yt-dlp flags, e.g. --limit-rate 500K. These can override the choices above; "
            "any conflict is shown below, never applied silently."
        )
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        group_layout.addWidget(hint)

        self.args_edit = QLineEdit()
        self.args_edit.setPlaceholderText("--limit-rate 500K --proxy http://127.0.0.1:8080")
        self.args_edit.textChanged.connect(self._on_text_changed)
        group_layout.addWidget(self.args_edit)

        self.error_label = QLabel("")
        self.error_label.setProperty("role", "error")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        group_layout.addWidget(self.error_label)

        self.url_warning_label = QLabel("")
        self.url_warning_label.setProperty("role", "warning")
        self.url_warning_label.setWordWrap(True)
        self.url_warning_label.hide()
        group_layout.addWidget(self.url_warning_label)

        self.conflict_label = QLabel("")
        self.conflict_label.setProperty("role", "warning")
        self.conflict_label.setWordWrap(True)
        self.conflict_label.hide()
        group_layout.addWidget(self.conflict_label)

        layout.addWidget(group)

    def _on_text_changed(self, text: str) -> None:
        self._last_result = parse_custom_args(text)

        if not self._last_result.ok:
            self.error_label.setText(f"⚠ {self._last_result.error_message}")
            self.error_label.show()
        else:
            self.error_label.hide()

        if self._last_result.ok and self._last_result.urls_in_args:
            urls = ", ".join(self._last_result.urls_in_args)
            self.url_warning_label.setText(
                f"⚠ URL(s) found in custom arguments ({urls}) — the URL to download is taken from "
                "the box above, not from here; this may not do what you expect."
            )
            self.url_warning_label.show()
        else:
            self.url_warning_label.hide()

        self.args_changed.emit()

    def is_valid(self) -> bool:
        return self._last_result.ok

    def current_overrides(self) -> dict:
        return self._last_result.overrides if self._last_result.ok else {}

    def show_conflicts(self, conflicts: list[str]) -> None:
        if conflicts:
            self.conflict_label.setText("⚠ Overriding GUI settings:\n" + "\n".join(f"• {c}" for c in conflicts))
            self.conflict_label.show()
        else:
            self.conflict_label.hide()
