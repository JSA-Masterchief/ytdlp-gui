"""Dark/light/system theme support.

Everything is built in code (palettes, a stylesheet, and a few tiny SVG
glyphs written to a temp folder for QSS to reference) with no external web
resources. The app always uses Qt's Fusion style so the theme fully controls
the colors: the native Windows 11 style mixes its own colors with the
palette, which leaves near-white text on light buttons. "system" follows the
OS light/dark setting, and switches live if the user changes it.

Widgets opt into styles with dynamic properties, e.g.
``button.setProperty("variant", "primary")`` or ``frame.setProperty("card", True)``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox

from app.constants import SUPPORTED_THEMES

TOKENS = {
    "light": {
        "bg": "#f4f5f7",
        "surface": "#ffffff",
        "surface2": "#f7f8fa",
        "hover": "#eef0f3",
        "border": "#e3e6eb",
        "border_strong": "#cdd2da",
        "text": "#111827",
        "muted": "#6b7280",
        "accent": "#2563eb",
        "accent_hover": "#1d4ed8",
        "accent_pressed": "#1e40af",
        "accent_soft": "#e8efff",
        "accent_soft_text": "#1d4ed8",
        "danger": "#dc2626",
        "danger_soft": "#fdecec",
        "success": "#15803d",
        "warning": "#b45309",
        "disabled_bg": "#e5e7eb",
        "disabled_text": "#9ca3af",
        "selection": "#dbe6ff",
    },
    "dark": {
        "bg": "#17181b",
        "surface": "#212226",
        "surface2": "#292a2f",
        "hover": "#2f3036",
        "border": "#32343a",
        "border_strong": "#43464e",
        "text": "#e7e8eb",
        "muted": "#9aa0aa",
        "accent": "#4f8cff",
        "accent_hover": "#6a9dff",
        "accent_pressed": "#3b78ea",
        "accent_soft": "#1f2b45",
        "accent_soft_text": "#9dbdff",
        "danger": "#f26b6b",
        "danger_soft": "#3a2224",
        "success": "#4ade80",
        "warning": "#f0b44c",
        "disabled_bg": "#2a2b30",
        "disabled_text": "#6b7079",
        "selection": "#263a63",
    },
}

ACCENT = QColor(TOKENS["light"]["accent"])
ACCENT_DARK = QColor(TOKENS["dark"]["accent"])

_STYLESHEET = """
* { outline: 0; }
QWidget { color: %(text)s; }
QMainWindow, QStackedWidget, QStackedWidget > QWidget { background: %(bg)s; }
QScrollArea { background: %(bg)s; border: none; }
QWidget#scrollContent { background: %(bg)s; }
QToolTip { background: %(surface)s; color: %(text)s; border: 1px solid %(border_strong)s; padding: 5px 8px; border-radius: 6px; }

/* ---------- Sidebar ---------- */
QFrame#sidebar { background: %(surface)s; border: none; border-right: 1px solid %(border)s; }
QLabel#brandTitle { font-size: 15px; font-weight: 700; }
QLabel#brandSubtitle { color: %(muted)s; font-size: 11px; }
QListWidget#navList { border: none; background: transparent; }
QListWidget#navList::item { padding: 9px 10px; margin: 2px 8px; border-radius: 8px; color: %(text)s; }
QListWidget#navList::item:hover:!selected { background: %(hover)s; }
QListWidget#navList::item:selected { background: %(accent_soft)s; color: %(accent_soft_text)s; font-weight: 600; }

/* ---------- Page headings & text roles ---------- */
QLabel[role="pageTitle"] { font-size: 20px; font-weight: 700; }
QLabel[role="pageSubtitle"], QLabel[role="muted"] { color: %(muted)s; }
QLabel[role="sectionTitle"] { font-size: 13px; font-weight: 700; }
QLabel[role="fieldLabel"] { color: %(muted)s; font-size: 12px; font-weight: 600; }
QLabel[role="error"] { color: %(danger)s; }
QLabel[role="success"] { color: %(success)s; }
QLabel[role="warning"] { color: %(warning)s; }
QLabel[role="mediaTitle"] { font-size: 16px; font-weight: 700; }
QLabel[role="emptyTitle"] { font-size: 15px; font-weight: 700; }
QLabel#thumbnail { background: %(surface2)s; border-radius: 8px; color: %(muted)s; }

/* ---------- Cards ---------- */
QFrame[card="true"] { background: %(surface)s; border: 1px solid %(border)s; border-radius: 12px; }
QFrame[card="true"] QLabel, QFrame[card="true"] QCheckBox { background: transparent; }
QFrame[banner="success"] { background: %(accent_soft)s; border: 1px solid %(accent)s; border-radius: 10px; }
QFrame[banner="error"] { background: %(danger_soft)s; border: 1px solid %(danger)s; border-radius: 10px; }
QFrame#actionBar { background: %(surface)s; border: none; border-top: 1px solid %(border)s; }

/* ---------- Group boxes (Settings, Advanced) ---------- */
QGroupBox {
    background: %(surface)s; border: 1px solid %(border)s; border-radius: 12px;
    margin-top: 22px; padding: 14px 12px 12px 12px; font-weight: 700;
}
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 4px; top: 2px; padding: 0 4px; color: %(text)s; }
QGroupBox QLabel, QGroupBox QCheckBox { font-weight: normal; background: transparent; }

/* ---------- Inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background: %(surface)s; border: 1px solid %(border_strong)s; border-radius: 8px;
    padding: 6px 10px; selection-background-color: %(accent)s; selection-color: white;
    min-height: 20px;
}
QTextEdit, QPlainTextEdit { padding: 6px 8px; }
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: %(muted)s; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid %(accent)s; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QTextEdit:disabled { background: %(surface2)s; color: %(disabled_text)s; border-color: %(border)s; }
QTextEdit#urlInput { font-size: 14px; border-radius: 10px; padding: 8px 12px; }
QPlainTextEdit#commandPreview, QPlainTextEdit#logView { font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; background: %(surface2)s; }

QComboBox { padding-right: 30px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 28px; border: none; }
QComboBox::down-arrow { image: url("%(chevron)s"); width: 14px; height: 14px; }
QComboBox::down-arrow:disabled { image: url("%(chevron_disabled)s"); }
QComboBox QAbstractItemView {
    background: %(surface)s; border: 1px solid %(border_strong)s; border-radius: 8px; padding: 4px;
    selection-background-color: %(accent_soft)s; selection-color: %(accent_soft_text)s; outline: 0;
}
QSpinBox { padding-right: 26px; }
QSpinBox::up-button, QSpinBox::down-button { subcontrol-origin: border; width: 22px; border: none; background: transparent; }
QSpinBox::up-button { subcontrol-position: top right; margin: 3px 3px 0 0; }
QSpinBox::down-button { subcontrol-position: bottom right; margin: 0 3px 3px 0; }
QSpinBox::up-arrow { image: url("%(chevron_up)s"); width: 11px; height: 11px; }
QSpinBox::down-arrow { image: url("%(chevron)s"); width: 11px; height: 11px; }

QCheckBox { spacing: 8px; padding: 2px 0; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid %(border_strong)s; border-radius: 4px; background: %(surface)s; }
QCheckBox::indicator:hover { border-color: %(accent)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; image: url("%(check)s"); }
QCheckBox::indicator:disabled { background: %(surface2)s; border-color: %(border)s; }
QCheckBox::indicator:checked:disabled { background: %(disabled_bg)s; }
QCheckBox:disabled { color: %(disabled_text)s; }

/* ---------- Buttons ---------- */
QPushButton, QToolButton {
    background: %(surface)s; color: %(text)s; border: 1px solid %(border_strong)s;
    border-radius: 8px; padding: 7px 14px; font-weight: 600;
}
QPushButton:hover, QToolButton:hover { background: %(hover)s; border-color: %(muted)s; }
QPushButton:pressed, QToolButton:pressed { background: %(border)s; }
QPushButton:disabled, QToolButton:disabled { color: %(disabled_text)s; background: %(surface2)s; border-color: %(border)s; }

QPushButton[variant="primary"], QPushButton[primary="true"] {
    background: %(accent)s; color: white; border: 1px solid %(accent)s; padding: 8px 20px;
}
QPushButton[variant="primary"]:hover, QPushButton[primary="true"]:hover { background: %(accent_hover)s; border-color: %(accent_hover)s; }
QPushButton[variant="primary"]:pressed, QPushButton[primary="true"]:pressed { background: %(accent_pressed)s; }
QPushButton[variant="primary"]:disabled, QPushButton[primary="true"]:disabled { background: %(disabled_bg)s; border-color: %(disabled_bg)s; color: %(disabled_text)s; }
QPushButton[size="large"] { padding: 11px 26px; font-size: 14px; border-radius: 10px; }

QPushButton[variant="danger"] { color: %(danger)s; }
QPushButton[variant="danger"]:hover { background: %(danger_soft)s; border-color: %(danger)s; }

QPushButton[variant="ghost"], QToolButton[variant="ghost"] { background: transparent; border: 1px solid transparent; padding: 6px 8px; }
QPushButton[variant="ghost"]:hover, QToolButton[variant="ghost"]:hover { background: %(hover)s; border-color: transparent; }
QPushButton[variant="ghost"]:disabled { background: transparent; border-color: transparent; }
QPushButton[variant="icon"] { background: transparent; border: 1px solid transparent; padding: 5px; border-radius: 6px; }
QPushButton[variant="icon"]:hover { background: %(hover)s; border-color: %(border)s; }
QPushButton[variant="icon"]:disabled { background: transparent; border-color: transparent; }

QPushButton[variant="chip"] {
    background: %(surface)s; border: 1px solid %(border_strong)s; border-radius: 16px;
    padding: 6px 14px; font-weight: 600;
}
QPushButton[variant="chip"]:hover { border-color: %(accent)s; }
QPushButton[variant="chip"]:checked { background: %(accent_soft)s; color: %(accent_soft_text)s; border-color: %(accent)s; }
QPushButton[variant="chip"]:disabled { color: %(disabled_text)s; border-color: %(border)s; background: %(surface2)s; }

QFrame#sidebar QPushButton[variant="ghost"] { font-weight: 500; color: %(muted)s; text-align: left; padding: 8px 12px; margin: 0 8px; }
QFrame#sidebar QPushButton[variant="ghost"]:hover { color: %(text)s; }
QToolButton#advancedToggle { background: transparent; border: none; padding: 6px 2px; font-weight: 700; }
QToolButton#advancedToggle:hover { color: %(accent)s; }

/* ---------- Tables ---------- */
QTableWidget, QTableView {
    background: %(surface)s; alternate-background-color: %(surface2)s; border: 1px solid %(border)s;
    border-radius: 12px; gridline-color: transparent; selection-background-color: %(selection)s; selection-color: %(text)s;
}
QTableWidget::item { padding: 6px 8px; border: none; }
QHeaderView { background: transparent; }
QHeaderView::section {
    background: %(surface)s; color: %(muted)s; border: none; border-bottom: 1px solid %(border)s;
    padding: 8px; font-weight: 700; font-size: 12px;
}
QTableCornerButton::section { background: %(surface)s; border: none; }

/* ---------- Progress ---------- */
QProgressBar {
    background: %(hover)s; border: none; border-radius: 5px; text-align: center;
    color: %(text)s; font-size: 11px; font-weight: 600; min-height: 10px; max-height: 18px;
}
QProgressBar::chunk { background: %(accent)s; border-radius: 5px; }
QProgressBar[state="done"]::chunk { background: %(success)s; }
QProgressBar[state="failed"]::chunk { background: %(danger)s; }
QProgressBar#rowProgress { margin: 19px 12px 19px 4px; min-height: 8px; max-height: 8px; border-radius: 4px; }
QProgressBar#rowProgress::chunk { border-radius: 4px; }
QProgressBar#busyBar { max-height: 4px; min-height: 4px; border-radius: 2px; }
QProgressBar#busyBar::chunk { border-radius: 2px; }

/* ---------- Scrollbars ---------- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(border_strong)s; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: %(muted)s; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: %(border_strong)s; border-radius: 3px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: %(muted)s; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---------- Toast ---------- */
QFrame#toast { background: %(text)s; border-radius: 10px; }
QFrame#toast QLabel { color: %(bg)s; background: transparent; font-weight: 600; }
QFrame#toast QPushButton { background: transparent; color: %(toast_link)s; border: none; padding: 4px 8px; }

QMessageBox QPushButton { min-width: 70px; }
"""

_current_theme = "system"
_watching_system_scheme = False
_cursor_filter: QObject | None = None
_font_applied = False


def _palette_from_tokens(t: dict) -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.Window: t["bg"],
        QPalette.WindowText: t["text"],
        QPalette.Base: t["surface"],
        QPalette.AlternateBase: t["surface2"],
        QPalette.Text: t["text"],
        QPalette.PlaceholderText: t["muted"],
        QPalette.Button: t["surface"],
        QPalette.ButtonText: t["text"],
        QPalette.Highlight: t["accent"],
        QPalette.HighlightedText: "#ffffff",
        QPalette.Link: t["accent"],
        QPalette.ToolTipBase: t["surface"],
        QPalette.ToolTipText: t["text"],
        QPalette.Mid: t["border_strong"],
        QPalette.Midlight: t["border"],
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(t["disabled_text"]))
    return palette


def build_light_palette() -> QPalette:
    return _palette_from_tokens(TOKENS["light"])


def build_dark_palette() -> QPalette:
    return _palette_from_tokens(TOKENS["dark"])


def _system_prefers_dark() -> bool:
    hints = QGuiApplication.styleHints()
    return hints is not None and hints.colorScheme() == Qt.ColorScheme.Dark


def resolve_theme(theme: str) -> str:
    """Map a configured theme to the concrete "light" or "dark" to draw."""
    if theme == "dark" or (theme not in ("light", "dark") and _system_prefers_dark()):
        return "dark"
    return "light"


def current_tokens() -> dict:
    return TOKENS[resolve_theme(_current_theme)]


def _glyph_dir() -> Path:
    directory = Path(tempfile.gettempdir()) / "ytdlp-gui-theme"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_glyph(name: str, path_markup: str, color: str, stroke: float = 2.5) -> str:
    target = _glyph_dir() / f"{name}-{color.lstrip('#')}.svg"
    if not target.exists():
        target.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
            f"{path_markup}</svg>",
            encoding="utf-8",
        )
    return target.as_posix()


def build_stylesheet(name: str) -> str:
    t = TOKENS[name]
    values = dict(t)
    values["chevron"] = _write_glyph("chevron-down", '<path d="M6 9l6 6 6-6"/>', t["muted"])
    values["chevron_disabled"] = _write_glyph("chevron-down", '<path d="M6 9l6 6 6-6"/>', t["disabled_text"])
    values["chevron_up"] = _write_glyph("chevron-up", '<path d="M6 15l6-6 6 6"/>', t["muted"])
    values["check"] = _write_glyph("check", '<path d="M20 6L9 17l-5-5"/>', "#ffffff", stroke=3)
    values["toast_link"] = "#9dbdff" if name == "light" else "#1d4ed8"
    return _STYLESHEET % values


class _PointingCursorFilter(QObject):
    """Gives every clickable control a hand cursor, so it reads as clickable."""

    def eventFilter(self, obj, event):  # noqa: N802, ANN001
        if event.type() == QEvent.Polish and isinstance(obj, (QAbstractButton, QComboBox)):
            obj.setCursor(Qt.PointingHandCursor)
        return False


def _apply_base_font(app: QApplication) -> None:
    global _font_applied
    if _font_applied:
        return
    _font_applied = True
    font = QFont(app.font())
    if sys.platform == "win32":
        font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    font.setPointSizeF(max(font.pointSizeF(), 9.5))
    app.setFont(font)


def _on_system_scheme_changed(*_args) -> None:
    app = QApplication.instance()
    if app is not None and _current_theme == "system":
        apply_theme(app, "system")


def apply_theme(app: QApplication, theme: str) -> None:
    """Apply `theme` ("system" | "light" | "dark") to the whole application."""
    global _current_theme, _watching_system_scheme, _cursor_filter

    if theme not in SUPPORTED_THEMES:
        theme = "system"
    _current_theme = theme

    # Each of these restyles every live widget, so skip any that would be a
    # no-op (e.g. MainWindow re-applying the theme that is already active).
    if not app.property("ytdlpFusionApplied"):
        app.setStyle("Fusion")
        app.setProperty("ytdlpFusionApplied", True)
    _apply_base_font(app)

    name = resolve_theme(theme)
    if app.property("ytdlpThemeApplied") == name:
        return
    app.setProperty("ytdlpThemeApplied", name)
    app.setPalette(build_dark_palette() if name == "dark" else build_light_palette())
    app.setStyleSheet(build_stylesheet(name))

    if _cursor_filter is None:
        _cursor_filter = _PointingCursorFilter(app)
        app.installEventFilter(_cursor_filter)

    if not _watching_system_scheme:
        hints = QGuiApplication.styleHints()
        if hints is not None and hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(_on_system_scheme_changed)
            _watching_system_scheme = True

    from ui.icons import refresh_icons

    refresh_icons()


def next_theme(current: str) -> str:
    """Cycle order for the header's quick theme-toggle button."""
    order = ["system", "light", "dark"]
    try:
        idx = order.index(current)
    except ValueError:
        idx = 0
    return order[(idx + 1) % len(order)]
