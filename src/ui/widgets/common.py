"""Small reusable UI building blocks shared by the pages."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.icons import set_button_icon


def make_button(
    text: str = "",
    *,
    variant: str | None = None,
    icon: str | None = None,
    tooltip: str | None = None,
    size: str | None = None,
    parent: QWidget | None = None,
) -> QPushButton:
    button = QPushButton(text, parent)
    if variant:
        button.setProperty("variant", variant)
    if size:
        button.setProperty("size", size)
    if icon:
        set_button_icon(button, icon, role="on-accent" if variant == "primary" else "text")
    if tooltip:
        button.setToolTip(tooltip)
        if not text:
            button.setAccessibleName(tooltip)
    return button


def set_role(label: QLabel, role: str) -> QLabel:
    """Switch a label's text role (error/success/warning/muted...) and restyle it."""
    label.setProperty("role", role)
    label.style().unpolish(label)
    label.style().polish(label)
    return label


def make_label(text: str = "", role: str | None = None, *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if role:
        label.setProperty("role", role)
    label.setWordWrap(wrap)
    return label


class Card(QFrame):
    """A rounded, bordered surface that groups related content."""

    def __init__(self, parent: QWidget | None = None, *, margins: int = 16, spacing: int = 12) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(margins, margins, margins, margins)
        self.body.setSpacing(spacing)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title_label = make_label(title, "pageTitle")
        text_col.addWidget(self.title_label)
        if subtitle:
            self.subtitle_label = make_label(subtitle, "pageSubtitle", wrap=True)
            text_col.addWidget(self.subtitle_label)
        layout.addLayout(text_col, stretch=1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions)


class ResponsiveGrid(QWidget):
    """Lays out labelled fields in as many columns as the width allows,
    reflowing (e.g. 4 → 2 → 1 columns) as the window is resized."""

    def __init__(self, min_column_width: int = 190, max_columns: int = 4, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min_column_width = min_column_width
        self._max_columns = max_columns
        self._fields: list[QWidget] = []
        self._hidden_fields: set[int] = set()
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(12)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def add_field(self, label: str, widget: QWidget) -> QWidget:
        field = QWidget(self)
        column = QVBoxLayout(field)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        column.addWidget(make_label(label, "fieldLabel"))
        column.addWidget(widget)
        self._fields.append(field)
        self._relayout(force=True)
        return field

    def columns(self) -> int:
        return self._columns

    def set_field_visible(self, field: QWidget, visible: bool) -> None:
        """Show/hide a field and close the gap it leaves, rather than
        leaving an empty cell in the grid."""
        key = id(field)
        if (key not in self._hidden_fields) == visible:
            return
        if visible:
            self._hidden_fields.discard(key)
        else:
            self._hidden_fields.add(key)
        field.setVisible(visible)
        self._relayout(force=True)

    def _visible_fields(self) -> list[QWidget]:
        return [f for f in self._fields if id(f) not in self._hidden_fields]

    def _target_columns(self, width: int) -> int:
        fits = max(1, (width + 12) // (self._min_column_width + 12))
        return max(1, min(self._max_columns, fits, len(self._visible_fields()) or 1))

    def _relayout(self, force: bool = False) -> None:
        columns = self._target_columns(self.width() or self._min_column_width * self._max_columns)
        if columns == self._columns and not force:
            return
        self._columns = columns
        for field in self._fields:
            self._grid.removeWidget(field)
        for index, field in enumerate(self._visible_fields()):
            self._grid.addWidget(field, index // columns, index % columns)
        for col in range(self._max_columns):
            self._grid.setColumnStretch(col, 1 if col < columns else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802, ANN001
        super().resizeEvent(event)
        self._relayout()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._min_column_width, super().minimumSizeHint().height())


class EmptyState(QWidget):
    """Friendly placeholder shown when a list has nothing in it yet."""

    def __init__(
        self,
        icon: str,
        title: str,
        message: str,
        action_text: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 48, 24, 48)
        layout.setSpacing(8)
        layout.addStretch(1)

        badge = QPushButton()
        badge.setProperty("variant", "icon")
        badge.setEnabled(False)
        set_button_icon(badge, icon, role="muted", size=40)
        badge.setFixedSize(64, 64)
        layout.addWidget(badge, alignment=Qt.AlignHCenter)

        title_label = make_label(title, "emptyTitle")
        title_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(title_label)
        message_label = make_label(message, "muted", wrap=True)
        message_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(message_label)

        self.action_button: QPushButton | None = None
        if action_text:
            self.action_button = make_button(action_text, variant="primary")
            layout.addSpacing(8)
            layout.addWidget(self.action_button, alignment=Qt.AlignHCenter)
        layout.addStretch(2)


class Toast(QFrame):
    """A brief notification that slides into the bottom-right corner of its
    parent window and fades out on its own."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 8, 10)
        layout.setSpacing(8)
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label, stretch=1)
        self.action_button = QPushButton()
        self.action_button.clicked.connect(self._on_action)
        layout.addWidget(self.action_button)
        self._callback: Callable[[], None] | None = None

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(220)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(
        self,
        text: str,
        action_text: str | None = None,
        callback: Callable[[], None] | None = None,
        duration_ms: int = 4000,
    ) -> None:
        self.message_label.setText(text)
        self._callback = callback
        self.action_button.setVisible(bool(action_text))
        self.action_button.setText(action_text or "")
        self.setMaximumWidth(min(420, max(240, self.parentWidget().width() - 48)))
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(self._opacity.opacity() if self.isVisible() else 0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._hide_timer.start(duration_ms)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 20
        self.move(parent.width() - self.width() - margin, parent.height() - self.height() - margin)

    def _fade_out(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._fade.endValue() == 0.0:
            self.hide()

    def _on_action(self) -> None:
        if self._callback is not None:
            self._callback()
        self._fade_out()

    def reposition(self) -> None:
        if self.isVisible():
            self._reposition()
