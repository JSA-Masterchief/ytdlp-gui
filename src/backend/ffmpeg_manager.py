"""Detects FFmpeg/FFprobe on the system and reports their versions.

Never uses shell=True or shell string concatenation, per project security
requirements. Detection failures are returned as data (not exceptions) so
the UI can show a helpful setup screen instead of crashing.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger("ytdlp_gui")


@dataclass
class ExecutableStatus:
    name: str
    path: str | None
    found: bool
    version: str | None = None
    error: str | None = None


def _find_executable(name: str, configured_path: str | None) -> str | None:
    if configured_path:
        return configured_path if shutil.which(configured_path) or _is_executable_file(configured_path) else None
    return shutil.which(name)


def _is_executable_file(path: str) -> bool:
    import os

    return os.path.isfile(path) and os.access(path, os.X_OK)


def _get_version(path: str, version_flag: str = "-version") -> str | None:
    try:
        result = subprocess.run(
            [path, version_flag],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else None
        return first_line
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


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
