from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

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


def test_apply_theme_system_follows_os_dark_mode(qapp):
    with patch("ui.theme._system_prefers_dark", return_value=True):
        apply_theme(qapp, "system")
    assert qapp.palette().color(QPalette.Window).lightness() < 80


def test_apply_theme_system_follows_os_light_mode(qapp):
    with patch("ui.theme._system_prefers_dark", return_value=False):
        apply_theme(qapp, "system")
    assert qapp.palette().color(QPalette.Window).lightness() > 200


def test_apply_theme_rejects_unknown_value_falls_back_to_system(qapp):
    with patch("ui.theme._system_prefers_dark", return_value=False):
        apply_theme(qapp, "not_a_real_theme")
    assert qapp.palette().color(QPalette.Window).lightness() > 200


def test_apply_theme_uses_fusion_style(qapp):
    qapp.setProperty("ytdlpFusionApplied", None)
    with patch.object(qapp, "setStyle", wraps=qapp.setStyle) as set_style:
        apply_theme(qapp, "light")
    set_style.assert_called_with("Fusion")


def test_button_text_is_readable_in_both_themes(qapp):
    """Regression: the native Windows 11 style drew near-white button text
    on light buttons. Button text must contrast with the button color."""
    for theme in ("light", "dark"):
        apply_theme(qapp, theme)
        pal = qapp.palette()
        diff = abs(pal.color(QPalette.ButtonText).lightness() - pal.color(QPalette.Button).lightness())
        assert diff > 150, theme


def test_os_scheme_change_reapplies_only_when_following_system(qapp):
    from ui import theme as theme_module

    apply_theme(qapp, "light")
    with patch("ui.theme._system_prefers_dark", return_value=True):
        theme_module._on_system_scheme_changed()
    assert qapp.palette().color(QPalette.Window).lightness() > 200

    with patch("ui.theme._system_prefers_dark", return_value=True):
        apply_theme(qapp, "system")
        theme_module._on_system_scheme_changed()
    assert qapp.palette().color(QPalette.Window).lightness() < 80


class TestNextTheme:
    def test_cycles_system_to_light(self):
        assert next_theme("system") == "light"

    def test_cycles_light_to_dark(self):
        assert next_theme("light") == "dark"

    def test_cycles_dark_to_system(self):
        assert next_theme("dark") == "system"

    def test_unknown_value_defaults_to_first_in_cycle(self):
        assert next_theme("garbage") == "light"


def test_reapplying_the_active_theme_is_a_no_op(qapp):
    apply_theme(qapp, "dark")
    with patch.object(qapp, "setStyleSheet") as set_sheet:
        apply_theme(qapp, "dark")
    set_sheet.assert_not_called()


def test_stylesheet_builds_for_both_themes_with_existing_glyphs():
    from pathlib import Path
    import re

    from ui.theme import build_stylesheet

    for name in ("light", "dark"):
        sheet = build_stylesheet(name)
        assert "%(" not in sheet
        for url in re.findall(r'url\("([^"]+)"\)', sheet):
            assert Path(url).exists(), url
