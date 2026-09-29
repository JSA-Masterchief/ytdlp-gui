from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ui.widgets.custom_args_widget import CustomArgsWidget


def test_empty_by_default_no_error(qtbot):
    widget = CustomArgsWidget()
    qtbot.addWidget(widget)

    assert widget.is_valid()
    assert widget.error_label.isHidden()
    assert widget.current_overrides() == {}


def test_valid_args_show_no_error(qtbot):
    widget = CustomArgsWidget()
    qtbot.addWidget(widget)

    widget.args_edit.setText("--limit-rate 500K")

    assert widget.is_valid()
    assert widget.error_label.isHidden()
    assert widget.current_overrides().get("ratelimit") == 512000


def test_invalid_args_show_error_and_invalidate(qtbot):
    widget = CustomArgsWidget()
    qtbot.addWidget(widget)

    widget.args_edit.setText("--not-a-real-flag")

    assert not widget.is_valid()
    assert not widget.error_label.isHidden()
    assert widget.current_overrides() == {}


def test_url_in_args_shows_warning(qtbot):
    widget = CustomArgsWidget()
    qtbot.addWidget(widget)

    widget.args_edit.setText("https://example.com/video")

    assert not widget.url_warning_label.isHidden()


def test_no_url_no_warning(qtbot):
    widget = CustomArgsWidget()
    qtbot.addWidget(widget)

    widget.args_edit.setText("--limit-rate 500K")

    assert widget.url_warning_label.isHidden()


def test_args_changed_signal_fires_on_text_change(qtbot):
    widget = CustomArgsWidget()
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.args_changed, timeout=1000):
        widget.args_edit.setText("--limit-rate 500K")


def test_show_conflicts_displays_and_hides(qtbot):
    widget = CustomArgsWidget()
    qtbot.addWidget(widget)

    widget.show_conflicts(["format: GUI set 'best', custom arguments override to 'worst'"])
    assert not widget.conflict_label.isHidden()
    assert "format" in widget.conflict_label.text()

    widget.show_conflicts([])
    assert widget.conflict_label.isHidden()


def test_fixing_invalid_args_clears_error(qtbot):
    widget = CustomArgsWidget()
    qtbot.addWidget(widget)

    widget.args_edit.setText("--not-a-real-flag")
    assert not widget.is_valid()

    widget.args_edit.setText("--limit-rate 500K")
    assert widget.is_valid()
    assert widget.error_label.isHidden()
