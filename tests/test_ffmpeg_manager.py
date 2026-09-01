"""Tests for backend.ffmpeg_manager. Mocks shutil.which/subprocess so these
pass in any environment, whether or not FFmpeg is actually installed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.ffmpeg_manager import check_ffmpeg, check_ffprobe


def test_check_ffmpeg_found_reports_version():
    fake_result = MagicMock(stdout="ffmpeg version 6.1.1\nmore text")
    with (
        patch("backend.ffmpeg_manager.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("backend.ffmpeg_manager.subprocess.run", return_value=fake_result),
    ):
        status = check_ffmpeg()

    assert status.found is True
    assert status.path == "/usr/bin/ffmpeg"
    assert "6.1.1" in status.version


def test_check_ffmpeg_not_found_returns_helpful_status():
    with patch("backend.ffmpeg_manager.shutil.which", return_value=None):
        status = check_ffmpeg()

    assert status.found is False
    assert status.path is None
    assert status.error is not None


def test_check_ffprobe_not_found():
    with patch("backend.ffmpeg_manager.shutil.which", return_value=None):
        status = check_ffprobe()

    assert status.found is False
