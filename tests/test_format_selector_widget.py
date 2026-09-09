from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from formats.selector import MODE_AUDIO_ONLY, MODE_VIDEO_ONLY
from ui.widgets.format_selector_widget import FormatSelectorWidget


def test_default_selection_is_video_audio_mp4_best(qtbot):
    widget = FormatSelectorWidget()
    qtbot.addWidget(widget)

    selection = widget.current_selection()
    assert selection.mode != MODE_AUDIO_ONLY
    assert selection.container == "mp4"
    assert selection.quality == "best"


def test_switching_to_audio_only_disables_container_enables_audio_format(qtbot):
    widget = FormatSelectorWidget()
    qtbot.addWidget(widget)

    idx = widget.mode_combo.findData(MODE_AUDIO_ONLY)
    widget.mode_combo.setCurrentIndex(idx)

    assert not widget.container_combo.isEnabled()
    assert widget.audio_format_combo.isEnabled()
    assert widget.current_selection().mode == MODE_AUDIO_ONLY


def test_selection_changed_signal_fires_on_mode_change(qtbot):
    widget = FormatSelectorWidget()
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.selection_changed, timeout=1000):
        idx = widget.mode_combo.findData(MODE_VIDEO_ONLY)
        widget.mode_combo.setCurrentIndex(idx)


def test_set_available_heights_restricts_quality_options(qtbot):
    widget = FormatSelectorWidget()
    qtbot.addWidget(widget)

    widget.set_available_heights([1080, 720])

    labels = [widget.quality_combo.itemData(i) for i in range(widget.quality_combo.count())]
    assert "1080p" in labels
    assert "720p" in labels
    assert "480p" not in labels
    assert "best" in labels


def test_update_preview_populates_preview_box(qtbot):
    widget = FormatSelectorWidget()
    qtbot.addWidget(widget)

    widget.update_preview("https://example.com/video", "/tmp/downloads", "%(title)s.%(ext)s")

    text = widget.preview_box.toPlainText()
    assert text.startswith("yt-dlp -f")
    assert "example.com" in text
