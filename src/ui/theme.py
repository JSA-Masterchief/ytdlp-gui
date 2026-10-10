"""Dark/light/system theme support.

No external stylesheets or web resources — palettes only, built entirely
from Qt's own QPalette color roles, per the "UI must not depend on
external web resources" requirement. "system" means "don't touch the
palette at all" so the OS/Qt platform theme shows through untouched.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from app.constants import SUPPORTED_THEMES

_LIGHT_COLORS = {
    QPalette.Window: QColor(240, 240, 240),
    QPalette.WindowText: QColor(20, 20, 20),
    QPalette.Base: QColor(255, 255, 255),
    QPalette.AlternateBase: QColor(245, 245, 245),
    QPalette.Text: QColor(20, 20, 20),
    QPalette.Button: QColor(240, 240, 240),
    QPalette.ButtonText: QColor(20, 20, 20),
    QPalette.Highlight: QColor(51, 133, 255),
    QPalette.HighlightedText: QColor(255, 255, 255),
    QPalette.ToolTipBase: QColor(255, 255, 220),
    QPalette.ToolTipText: QColor(20, 20, 20),
}

_DARK_COLORS = {
    QPalette.Window: QColor(45, 45, 48),
    QPalette.WindowText: QColor(225, 225, 225),
    QPalette.Base: QColor(30, 30, 32),
    QPalette.AlternateBase: QColor(40, 40, 43),
    QPalette.Text: QColor(225, 225, 225),
    QPalette.Button: QColor(55, 55, 58),
    QPalette.ButtonText: QColor(225, 225, 225),
    QPalette.Highlight: QColor(60, 140, 255),
    QPalette.HighlightedText: QColor(255, 255, 255),
    QPalette.ToolTipBase: QColor(55, 55, 58),
    QPalette.ToolTipText: QColor(225, 225, 225),
    (QPalette.Disabled, QPalette.Text): QColor(130, 130, 130),
    (QPalette.Disabled, QPalette.WindowText): QColor(130, 130, 130),
    (QPalette.Disabled, QPalette.ButtonText): QColor(130, 130, 130),
}


def _build_palette(colors: dict) -> QPalette:
    palette = QPalette()
    for key, color in colors.items():
        if isinstance(key, tuple):
            group, role = key
            palette.setColor(group, role, color)
        else:
            palette.setColor(key, color)
    return palette


def build_light_palette() -> QPalette:
    return _build_palette(_LIGHT_COLORS)


def build_dark_palette() -> QPalette:
    return _build_palette(_DARK_COLORS)


def apply_theme(app: QApplication, theme: str) -> None:
    """Apply `theme` ("system" | "light" | "dark") to the whole application."""
    if theme not in SUPPORTED_THEMES:
        theme = "system"

    if theme == "system":
        app.setPalette(app.style().standardPalette())
    elif theme == "dark":
        app.setPalette(build_dark_palette())
    else:
        app.setPalette(build_light_palette())


def next_theme(current: str) -> str:
    """Cycle order for the header's quick theme-toggle button."""
    order = ["system", "light", "dark"]
    try:
        idx = order.index(current)
    except ValueError:
        idx = 0
    return order[(idx + 1) % len(order)]
