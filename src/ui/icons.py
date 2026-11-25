"""A small built-in line-icon set, rendered from inline SVG.

Icons are tinted to the current theme. Use `set_button_icon()` rather than
`button.setIcon()` so that `refresh_icons()` (called on every theme change)
can re-tint them; buttons with a colored background ask for "on-accent".
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QApplication

_PATHS: dict[str, str] = {
    "download": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/>',
    "queue": '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/>'
    '<path d="M3.5 6h.01"/><path d="M3.5 12h.01"/><path d="M3.5 18h.01"/>',
    "history": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    "settings": '<path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/>'
    '<path d="M20 21v-5"/><path d="M20 12V3"/><path d="M1 14h6"/><path d="M9 8h6"/><path d="M17 16h6"/>',
    "logs": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>'
    '<path d="M14 3v6h6"/><path d="M8 13h8"/><path d="M8 17h5"/>',
    "paste": '<rect x="8" y="2" width="8" height="4" rx="1"/>'
    '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "close": '<path d="M18 6L6 18"/><path d="M6 6l12 12"/>',
    "retry": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    "trash": '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="M4.9 4.9l1.4 1.4"/>'
    '<path d="M17.7 17.7l1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="M4.9 19.1l1.4-1.4"/>'
    '<path d="M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "system": '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "open": '<path d="M15 3h6v6"/><path d="M10 14L21 3"/>'
    '<path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
    "check": '<path d="M20 6L9 17l-5-5"/>',
    "video": '<rect x="2" y="6" width="14" height="12" rx="2"/><path d="M22 8l-6 4 6 4z"/>',
    "music": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "copy": '<rect x="9" y="9" width="13" height="13" rx="2"/>'
    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "save": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>'
    '<path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "chevron-right": '<path d="M9 6l6 6-6 6"/>',
    "alert": '<circle cx="12" cy="12" r="9"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/>'
    '<path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
}

ICON_NAMES = tuple(_PATHS)


def svg_markup(name: str, color: str, stroke_width: float = 2.0) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round">'
        f"{_PATHS[name]}</svg>"
    )


def make_icon(name: str, color: QColor | str, size: int = 48) -> QIcon:
    color_name = color.name() if isinstance(color, QColor) else color
    renderer = QSvgRenderer(QByteArray(svg_markup(name, color_name).encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    icon = QIcon(pixmap)
    # Same glyph for disabled state, just faded, so it never turns invisible.
    faded = QPixmap(pixmap.size())
    faded.fill(Qt.transparent)
    painter = QPainter(faded)
    painter.setOpacity(0.4)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    icon.addPixmap(faded, QIcon.Disabled)
    return icon


def _color_for(role: str) -> QColor:
    if role == "on-accent":
        return QColor("white")
    app = QApplication.instance()
    palette = app.palette() if app is not None else QPalette()
    if role == "accent":
        return palette.color(QPalette.Highlight)
    if role == "muted":
        return palette.color(QPalette.PlaceholderText)
    return palette.color(QPalette.ButtonText)


def set_button_icon(button: QAbstractButton, name: str, role: str = "text", size: int = 18) -> None:
    button.setProperty("iconName", name)
    button.setProperty("iconRole", role)
    button.setIconSize(QSize(size, size))
    button.setIcon(make_icon(name, _color_for(role)))


def refresh_icons() -> None:
    """Re-tint every themed icon after a palette change."""
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.allWidgets():
        if isinstance(widget, QAbstractButton):
            name = widget.property("iconName")
            if name:
                widget.setIcon(make_icon(name, _color_for(widget.property("iconRole") or "text")))
