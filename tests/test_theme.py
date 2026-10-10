from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QPalette

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ui.theme import apply_theme, build_dark_palette, build_light_palette, next_theme


def test_light_palette_has_light_window_background():
    palette = build_light_palette()
    color = palette.color(QPalette.Window)
    # "Light" means high lightness, not an exact color match.
    assert color.lightness() > 200


def test_dark_palette_has_dark_window_background():
    palette = build_dark_palette()
    color = palette.color(QPalette.Window)
    assert color.lightness() < 80


def test_dark_palette_text_is_light_for_contrast():
    palette = build_dark_palette()
    text_color = palette.color(QPalette.Text)
    assert text_color.lightness() > 180


def test_dark_palette_has_distinct_disabled_text_color():
    palette = build_dark_palette()
    normal = palette.color(QPalette.Active, QPalette.Text)
    disabled = palette.color(QPalette.Disabled, QPalette.Text)
    assert normal != disabled


def test_apply_theme_light_sets_light_window_color(qapp):
    apply_theme(qapp, "light")
    assert qapp.palette().color(QPalette.Window).lightness() > 200


def test_apply_theme_dark_sets_dark_window_color(qapp):
    apply_theme(qapp, "dark")
    assert qapp.palette().color(QPalette.Window).lightness() < 80


def test_apply_theme_system_does_not_crash_and_resets_to_style_default(qapp):
    apply_theme(qapp, "dark")
    apply_theme(qapp, "system")
    # No specific assertion on color — "system" means "whatever the
    # platform style provides" — just confirm it runs and actually
    # matches the style's own standard palette.
    assert qapp.palette().color(QPalette.Window) == qapp.style().standardPalette().color(QPalette.Window)


def test_apply_theme_rejects_unknown_value_falls_back_to_system(qapp):
    apply_theme(qapp, "not_a_real_theme")
    assert qapp.palette().color(QPalette.Window) == qapp.style().standardPalette().color(QPalette.Window)


class TestNextTheme:
    def test_cycles_system_to_light(self):
        assert next_theme("system") == "light"

    def test_cycles_light_to_dark(self):
        assert next_theme("light") == "dark"

    def test_cycles_dark_to_system(self):
        assert next_theme("dark") == "system"

    def test_unknown_value_defaults_to_first_in_cycle(self):
        assert next_theme("garbage") == "light"
