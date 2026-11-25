"""Detects FFmpeg/FFprobe on the system and reports their versions."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("ytdlp_gui")

# Keeps a console window from flashing up when the windowed (no-console)
# packaged build runs `ffmpeg -version`.
_NO_WINDOW_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


@dataclass
class ExecutableStatus:
    name: str
    path: str | None
    found: bool
    version: str | None = None
    error: str | None = None


def bundled_tools_dir() -> Path | None:
    """Directory of the packaged .exe, where a portable build can ship
    ffmpeg.exe/ffprobe.exe alongside it. None when running from source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def _bundled_executable(name: str) -> str | None:
    """ffmpeg placed next to the exe, or embedded inside a one-file build
    (unpacked to sys._MEIPASS at runtime)."""
    tools_dir = bundled_tools_dir()
    if tools_dir is None:
        return None
    filename = f"{name}.exe" if sys.platform == "win32" else name
    search = [tools_dir]
    embedded = getattr(sys, "_MEIPASS", None)
    if embedded:
        search.append(Path(embedded))
    for directory in search:
        candidate = directory / filename
        if _is_executable_file(str(candidate)):
            return str(candidate)
    return None


def _find_executable(name: str, configured_path: str | None) -> str | None:
    if configured_path:
        return configured_path if shutil.which(configured_path) or _is_executable_file(configured_path) else None
    return shutil.which(name) or _bundled_executable(name)


def _is_executable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _get_version(path: str, version_flag: str = "-version") -> str | None:
    try:
        result = subprocess.run(
            [path, version_flag],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=_NO_WINDOW_FLAGS,
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else None
        return first_line
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def resolve_ffmpeg_location(configured_path: str | None = None) -> str | None:
    """The value to pass as yt-dlp's `ffmpeg_location` option, or None to
    let yt-dlp search PATH itself.

    A path configured in Settings always wins. Otherwise, an ffmpeg bundled
    next to the packaged .exe is used only if none is on PATH.
    """
    if configured_path:
        return configured_path
    if shutil.which("ffmpeg"):
        return None
    return _bundled_executable("ffmpeg")


def check_ffmpeg(configured_path: str | None = None) -> ExecutableStatus:
    path = _find_executable("ffmpeg", configured_path)
    if not path:
        return ExecutableStatus(name="ffmpeg", path=None, found=False, error="FFmpeg not found on PATH")
    version = _get_version(path)
    return ExecutableStatus(name="ffmpeg", path=path, found=True, version=version)


def check_ffprobe(configured_path: str | None = None) -> ExecutableStatus:
    path = _find_executable("ffprobe", configured_path)
    if not path:
        return ExecutableStatus(name="ffprobe", path=None, found=False, error="FFprobe not found on PATH")
    version = _get_version(path)
    return ExecutableStatus(name="ffprobe", path=path, found=True, version=version)
