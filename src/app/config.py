"""Application configuration: schema, defaults, load/save, migration.

Configuration is stored as JSON in the per-user app-data directory (see
utils/paths.py). This module must handle a missing file, a corrupted file,
and older schema versions gracefully — it should never crash the app on
startup.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.constants import (
    CONFIG_FILENAME,
    DEFAULT_MAX_CONCURRENT_DOWNLOADS,
    DEFAULT_THEME,
)
from utils.paths import get_app_data_dir, get_default_download_dir

logger = logging.getLogger("ytdlp_gui")

CONFIG_SCHEMA_VERSION = 1


@dataclass
class AppConfig:
    schema_version: int = CONFIG_SCHEMA_VERSION
    theme: str = DEFAULT_THEME
    download_directory: str = field(default_factory=lambda: str(get_default_download_dir()))
    max_concurrent_downloads: int = DEFAULT_MAX_CONCURRENT_DOWNLOADS
    ytdlp_path: str | None = None
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None
    filename_template: str = "%(title)s [%(id)s].%(ext)s"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        # Only accept known fields; unknown/legacy keys are dropped rather
        # than causing a crash. Add migration steps here as schema evolves.
        known_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


def get_config_path() -> Path:
    return get_app_data_dir() / CONFIG_FILENAME


def load_config() -> AppConfig:
    path = get_config_path()
    if not path.exists():
        logger.info("No config file found at %s, using defaults.", path)
        return AppConfig()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return AppConfig.from_dict(raw)
    except (json.JSONDecodeError, OSError, TypeError) as exc:
        logger.warning("Config file at %s is corrupted (%s); resetting to defaults.", path, exc)
        return AppConfig()


def save_config(config: AppConfig) -> None:
    path = get_config_path()
    try:
        path.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to save config to %s: %s", path, exc)
