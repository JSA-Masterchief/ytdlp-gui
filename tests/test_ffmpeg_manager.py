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


def _make_fake_exe(directory, name):
    exe = directory / (f"{name}.exe" if sys.platform == "win32" else name)
    exe.write_bytes(b"")
    exe.chmod(0o755)
    return exe


def test_bundled_tools_dir_is_none_when_running_from_source():
    from backend.ffmpeg_manager import bundled_tools_dir

    with patch.object(sys, "frozen", False, create=True):
        assert bundled_tools_dir() is None


def test_check_ffmpeg_finds_exe_bundled_next_to_frozen_app(tmp_path):
    exe = _make_fake_exe(tmp_path, "ffmpeg")
    with (
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "executable", str(tmp_path / "ytdlp-gui.exe")),
        patch("backend.ffmpeg_manager.shutil.which", return_value=None),
        patch("backend.ffmpeg_manager.subprocess.run", return_value=MagicMock(stdout="ffmpeg version 7\n")),
    ):
        status = check_ffmpeg()
    assert status.found
    assert status.path == str(exe)


def test_resolve_location_prefers_configured_path():
    from backend.ffmpeg_manager import resolve_ffmpeg_location

    with patch("backend.ffmpeg_manager.shutil.which", return_value="/usr/bin/ffmpeg"):
        assert resolve_ffmpeg_location("C:/tools/ffmpeg.exe") == "C:/tools/ffmpeg.exe"


def test_resolve_location_defers_to_path_when_ffmpeg_is_on_path(tmp_path):
    from backend.ffmpeg_manager import resolve_ffmpeg_location

    _make_fake_exe(tmp_path, "ffmpeg")
    with (
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "executable", str(tmp_path / "ytdlp-gui.exe")),
        patch("backend.ffmpeg_manager.shutil.which", return_value="/usr/bin/ffmpeg"),
    ):
        assert resolve_ffmpeg_location(None) is None


def test_resolve_location_uses_bundled_exe_when_not_on_path(tmp_path):
    from backend.ffmpeg_manager import resolve_ffmpeg_location

    exe = _make_fake_exe(tmp_path, "ffmpeg")
    with (
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "executable", str(tmp_path / "ytdlp-gui.exe")),
        patch("backend.ffmpeg_manager.shutil.which", return_value=None),
    ):
        assert resolve_ffmpeg_location(None) == str(exe)


def test_resolve_location_is_none_when_nothing_found():
    from backend.ffmpeg_manager import resolve_ffmpeg_location

    with patch("backend.ffmpeg_manager.shutil.which", return_value=None):
        assert resolve_ffmpeg_location(None) is None
