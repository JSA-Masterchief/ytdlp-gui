from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from formats.advanced_options import SUBTITLE_MODE_ALL, SUBTITLE_MODE_NONE
from ui.widgets.advanced_options_widget import AdvancedOptionsWidget


def test_collapsed_by_default(qtbot):
    widget = AdvancedOptionsWidget()
    qtbot.addWidget(widget)

    assert not widget.toggle_button.isChecked()
    assert widget.content.isHidden()


def test_toggle_expands_content(qtbot):
    widget = AdvancedOptionsWidget()
    qtbot.addWidget(widget)

    widget.toggle_button.click()

    assert widget.toggle_button.isChecked()
    assert not widget.content.isHidden()


def test_default_options_are_all_off(qtbot):
    widget = AdvancedOptionsWidget()
    qtbot.addWidget(widget)

    options = widget.current_options()
    assert options.subtitles.mode == SUBTITLE_MODE_NONE
    assert options.sponsorblock.enabled is False
    assert options.chapters.embed_chapters is False
    assert options.metadata.embed_metadata is False


def test_subtitle_mode_none_disables_related_controls(qtbot):
    widget = AdvancedOptionsWidget()
    qtbot.addWidget(widget)

    assert not widget.subtitle_languages_edit.isEnabled()
    assert not widget.subtitle_embed_checkbox.isEnabled()


def test_selecting_subtitle_mode_enables_controls_and_reflects_in_options(qtbot):
    widget = AdvancedOptionsWidget()
    qtbot.addWidget(widget)

    idx = widget.subtitle_mode_combo.findData(SUBTITLE_MODE_ALL)
    widget.subtitle_mode_combo.setCurrentIndex(idx)
    widget.subtitle_languages_edit.setText("en,es")
    widget.subtitle_embed_checkbox.setChecked(True)

    assert widget.subtitle_languages_edit.isEnabled()

    options = widget.current_options()
    assert options.subtitles.mode == SUBTITLE_MODE_ALL
    assert options.subtitles.languages == ["en", "es"]
    assert options.subtitles.embed is True


def test_sponsorblock_checkboxes_disabled_until_enabled(qtbot):
    widget = AdvancedOptionsWidget()
    qtbot.addWidget(widget)

    assert not widget.sponsorblock_action_combo.isEnabled()
    for checkbox in widget._sponsorblock_category_checkboxes.values():
        assert not checkbox.isEnabled()

    widget.sponsorblock_enabled_checkbox.setChecked(True)

    assert widget.sponsorblock_action_combo.isEnabled()
    for checkbox in widget._sponsorblock_category_checkboxes.values():
        assert checkbox.isEnabled()


def test_sponsorblock_options_reflect_selected_categories(qtbot):
    widget = AdvancedOptionsWidget()
    qtbot.addWidget(widget)

    widget.sponsorblock_enabled_checkbox.setChecked(True)
    widget._sponsorblock_category_checkboxes["sponsor"].setChecked(True)
    widget._sponsorblock_category_checkboxes["intro"].setChecked(True)
    widget._sponsorblock_category_checkboxes["outro"].setChecked(False)

    options = widget.current_options()
    assert options.sponsorblock.enabled is True
    assert set(options.sponsorblock.categories) == {"sponsor", "intro"}


def test_options_changed_signal_fires_on_checkbox_toggle(qtbot):
    widget = AdvancedOptionsWidget()
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.options_changed, timeout=1000):
        widget.embed_metadata_checkbox.setChecked(True)


def test_empty_languages_field_defaults_to_english(qtbot):
    widget = AdvancedOptionsWidget()
    qtbot.addWidget(widget)

    idx = widget.subtitle_mode_combo.findData(SUBTITLE_MODE_ALL)
    widget.subtitle_mode_combo.setCurrentIndex(idx)
    widget.subtitle_languages_edit.setText("")

    assert widget.current_options().subtitles.languages == ["en"]


def test_set_available_languages_prefills_when_empty(qtbot):
    widget = AdvancedOptionsWidget()
    qtbot.addWidget(widget)

    widget.subtitle_languages_edit.setText("")
    widget.set_available_languages(["fr", "de"])

    assert widget.subtitle_languages_edit.text() == "fr"


def test_set_available_languages_does_not_override_user_input(qtbot):
    widget = AdvancedOptionsWidget()
    qtbot.addWidget(widget)

    widget.subtitle_languages_edit.setText("en")
    widget.set_available_languages(["fr", "de"])

    assert widget.subtitle_languages_edit.text() == "en"
