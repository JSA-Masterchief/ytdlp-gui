"""The raw "Custom yt-dlp Arguments" box: lets an advanced user type real
yt-dlp CLI flags, validates them live against yt-dlp's own parser, and
surfaces any conflicts with what the GUI's own controls already set —
never silently overriding anything without saying so.
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
    """Emits args_changed whenever the parsed result changes (valid or
    not) so the owning page can recompute the command preview and decide
    whether Download should be blocked on a parse error.
    """

    args_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_result = CustomArgsResult(ok=True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        group = QGroupBox("Custom yt-dlp Arguments (advanced)")
        group_layout = QVBoxLayout(group)

        hint = QLabel(
            "Type real yt-dlp command-line flags here, e.g. --limit-rate 500K --proxy socks5://127.0.0.1:1080\n"
            "These can override the settings chosen above — any conflict is shown below, never applied silently."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        group_layout.addWidget(hint)

        self.args_edit = QLineEdit()
        self.args_edit.setPlaceholderText("--limit-rate 500K --proxy http://127.0.0.1:8080")
        self.args_edit.textChanged.connect(self._on_text_changed)
        group_layout.addWidget(self.args_edit)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #c0392b;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        group_layout.addWidget(self.error_label)

        self.url_warning_label = QLabel("")
        self.url_warning_label.setStyleSheet("color: #b8860b;")
        self.url_warning_label.setWordWrap(True)
        self.url_warning_label.hide()
        group_layout.addWidget(self.url_warning_label)

        self.conflict_label = QLabel("")
        self.conflict_label.setStyleSheet("color: #b8860b;")
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

        # Conflicts against GUI options are computed by the owning page
        # (which knows the current base options) via show_conflicts(),
        # not here — this widget only knows about parsing, not the rest
        # of the form's state.
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
