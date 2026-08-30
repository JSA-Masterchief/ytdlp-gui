"""Application-wide constants.

Centralizing these avoids magic strings scattered across the codebase and
makes future internationalization / rebranding easier.
"""

from __future__ import annotations

APP_NAME = "yt-dlp GUI"
APP_ORG = "ytdlp-gui"
APP_VERSION = "0.1.0"

# Name of the per-user config file (see utils/paths.py for the directory).
CONFIG_FILENAME = "config.json"
HISTORY_FILENAME = "history.json"
LOG_FILENAME = "app.log"

DEFAULT_MAX_CONCURRENT_DOWNLOADS = 2
MAX_CONCURRENT_DOWNLOADS_LIMIT = 8

SUPPORTED_THEMES = ("system", "light", "dark")
DEFAULT_THEME = "system"
