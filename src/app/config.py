"""Application configuration: schema, defaults, migration, load/save.

Loading never raises and never discards good settings because of one bad
one: the file is migrated to the current schema, then each field is
validated individually (invalid fields fall back to their default; numeric
fields are clamped into their legal range). A file that isn't a JSON
object at all is moved aside to `config.json.corrupt` rather than being
silently overwritten by the next save, so the user's data isn't destroyed.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.constants import (
    CONFIG_FILENAME,
    DEFAULT_MAX_CONCURRENT_DOWNLOADS,
    DEFAULT_THEME,
    MAX_CONCURRENT_DOWNLOADS_LIMIT,
    SUPPORTED_THEMES,
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
        """Build a config from untrusted data: unknown keys are dropped and
        every known field is validated, falling back to its default.
        """
        return cls(**_sanitize(data))


# --- migration ---------------------------------------------------------------

# Legacy (schema 0 / unversioned) key names -> current names. These
# illustrate the migration mechanism: no earlier release ever shipped, so
# the old names are representative rather than historical.
_V0_RENAMES = {
    "download_dir": "download_directory",
    "concurrent_downloads": "max_concurrent_downloads",
    "output_template": "filename_template",
}


def _migrate_v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(data)
    for old_key, new_key in _V0_RENAMES.items():
        if old_key in migrated:
            value = migrated.pop(old_key)
            # An explicitly-present new-style key wins over a stale old one.
            migrated.setdefault(new_key, value)
    migrated["schema_version"] = 1
    return migrated


# from-version -> function producing the next version
_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    0: _migrate_v0_to_v1,
}


def migrate_config(raw: Any) -> dict[str, Any]:
    """Bring raw loaded JSON up to CONFIG_SCHEMA_VERSION.

    Raises ValueError if `raw` isn't a JSON object. Configs from a *newer*
    schema than this build understands are passed through unchanged
    (unknown fields are dropped later by sanitization) rather than being
    downgraded or rejected.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be an object, got {type(raw).__name__}")

    version = raw.get("schema_version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        version = 0

    data = dict(raw)
    while version < CONFIG_SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            break
        data = step(data)
        version += 1
    return data


# --- validation --------------------------------------------------------------


def _is_real_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _sanitize(data: dict[str, Any]) -> dict[str, Any]:
    """Return only the valid, known fields of `data`, normalized."""
    clean: dict[str, Any] = {}

    theme = data.get("theme")
    if isinstance(theme, str) and theme in SUPPORTED_THEMES:
        clean["theme"] = theme

    directory = data.get("download_directory")
    if isinstance(directory, str) and directory.strip():
        clean["download_directory"] = directory.strip()

    concurrent = data.get("max_concurrent_downloads")
    if _is_real_int(concurrent):
        clean["max_concurrent_downloads"] = max(1, min(concurrent, MAX_CONCURRENT_DOWNLOADS_LIMIT))

    for path_key in ("ytdlp_path", "ffmpeg_path", "ffprobe_path"):
        value = data.get(path_key)
        if isinstance(value, str):
            clean[path_key] = value.strip() or None

    template = data.get("filename_template")
    if isinstance(template, str) and template.strip():
        clean["filename_template"] = template.strip()

    version = data.get("schema_version")
    if _is_real_int(version) and version >= 0:
        clean["schema_version"] = version

    return clean


# --- load / save -------------------------------------------------------------


def get_config_path() -> Path:
    return get_app_data_dir() / CONFIG_FILENAME


def _backup_corrupt_file(path: Path) -> None:
    backup = path.with_name(path.name + ".corrupt")
    try:
        os.replace(path, backup)
        logger.warning("Moved unusable config file to %s", backup)
    except OSError as exc:
        logger.warning("Could not back up unusable config file %s: %s", path, exc)


def load_config() -> AppConfig:
    path = get_config_path()
    if not path.exists():
        logger.info("No config file found at %s, using defaults.", path)
        return AppConfig()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        migrated = migrate_config(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        logger.warning("Config file at %s is unusable (%s); using defaults.", path, exc)
        _backup_corrupt_file(path)
        return AppConfig()
    except OSError as exc:
        logger.warning("Could not read config file at %s (%s); using defaults.", path, exc)
        return AppConfig()

    config = AppConfig.from_dict(migrated)
    config.schema_version = CONFIG_SCHEMA_VERSION
    return config


def save_config(config: AppConfig) -> None:
    """Write atomically (temp file, then replace) so a crash mid-write can
    never leave a truncated config.json behind.
    """
    path = get_config_path()
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        tmp_path.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.error("Failed to save config to %s: %s", path, exc)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
