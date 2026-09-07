from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.models import FormatInfo
from formats.parser import (
    available_video_heights,
    describe_format,
    format_filesize,
    has_audio_only_formats,
)

VIDEO_1080 = FormatInfo(format_id="137", ext="mp4", resolution="1920x1080", vcodec="avc1", acodec="none")
VIDEO_720 = FormatInfo(format_id="136", ext="mp4", resolution="1280x720", vcodec="avc1", acodec="none")
AUDIO_M4A = FormatInfo(format_id="140", ext="m4a", vcodec="none", acodec="mp4a.40.2", abr=128.0)
COMBINED = FormatInfo(format_id="18", ext="mp4", resolution="640x360", vcodec="avc1", acodec="mp4a")


def test_available_video_heights_sorted_descending():
    heights = available_video_heights([VIDEO_720, VIDEO_1080, AUDIO_M4A])
    assert heights == [1080, 720]


def test_available_video_heights_ignores_audio_only():
    heights = available_video_heights([AUDIO_M4A])
    assert heights == []


def test_available_video_heights_parses_p_notation():
    fmt = FormatInfo(format_id="x", ext="mp4", resolution="1080p60", vcodec="avc1", acodec="none")
    assert available_video_heights([fmt]) == [1080]


def test_has_audio_only_formats_true():
    assert has_audio_only_formats([VIDEO_1080, AUDIO_M4A])


def test_has_audio_only_formats_false():
    assert not has_audio_only_formats([VIDEO_1080, COMBINED])


def test_format_filesize_bytes():
    assert format_filesize(500) == "500 B"


def test_format_filesize_mb():
    assert format_filesize(5 * 1024 * 1024) == "5.0 MB"


def test_format_filesize_unknown():
    assert format_filesize(None) == "Unknown size"


def test_describe_format_includes_key_details():
    fmt = FormatInfo(
        format_id="137",
        ext="mp4",
        resolution="1920x1080",
        fps=30,
        vcodec="avc1.640028",
        acodec="none",
        filesize=1_048_576,
    )
    description = describe_format(fmt)
    assert "1920x1080" in description
    assert "30fps" in description
    assert "avc1.640028" in description
    assert "1.0 MB" in description
