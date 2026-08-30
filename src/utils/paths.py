"""Resolves per-user application data directories.

Never write configuration next to the executable — always use the proper
per-OS app-data location. On Windows this is %APPDATA%, with sane fallbacks
for other platforms so the codebase stays portable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.constants import APP_ORG


def get_app_data_dir() -> Path:
    """Return (and create if needed) the per-user app-data directory."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home() / ".config"

    app_dir = root / APP_ORG
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_default_download_dir() -> Path:
    """Return the OS default Downloads folder, falling back to home."""
    candidate = Path.home() / "Downloads"
    return candidate if candidate.exists() else Path.home()


def get_log_file_path() -> Path:
    from app.constants import LOG_FILENAME

    return get_app_data_dir() / LOG_FILENAME
