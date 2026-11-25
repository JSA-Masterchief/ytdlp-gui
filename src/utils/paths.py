"""Resolves per-user application data directories."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.constants import APP_ORG


def get_app_data_dir() -> Path:
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
    candidate = Path.home() / "Downloads"
    return candidate if candidate.exists() else Path.home()


def get_log_file_path() -> Path:
    from app.constants import LOG_FILENAME

    return get_app_data_dir() / LOG_FILENAME


def get_history_file_path() -> Path:
    from app.constants import HISTORY_FILENAME

    return get_app_data_dir() / HISTORY_FILENAME


def get_resource_path(relative: str) -> Path:
    """Locate a bundled read-only asset (e.g. "assets/icon.ico").

    In a PyInstaller build, data files are unpacked under sys._MEIPASS;
    from source they live at the repository root.
    """
    bundle_root = getattr(sys, "_MEIPASS", None)
    root = Path(bundle_root) if bundle_root else Path(__file__).resolve().parent.parent.parent
    return root / relative


def get_window_state_path() -> Path:
    """Where the main window remembers its size and position between runs."""
    return get_app_data_dir() / "window_state.bin"
