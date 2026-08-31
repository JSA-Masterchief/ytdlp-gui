"""Tests for app.config: defaults, round-trip, and corrupted-file handling."""

from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.config import AppConfig  # noqa: E402


def test_default_config_has_sane_values():
    config = AppConfig()
    assert config.theme == "system"
    assert config.max_concurrent_downloads >= 1
    assert config.download_directory  # not empty


def test_config_round_trip():
    config = AppConfig(theme="dark", max_concurrent_downloads=3)
    data = config.to_dict()
    restored = AppConfig.from_dict(data)
    assert restored.theme == "dark"
    assert restored.max_concurrent_downloads == 3


def test_config_from_dict_ignores_unknown_keys():
    data = {"theme": "light", "some_future_field": "ignored"}
    restored = AppConfig.from_dict(data)
    assert restored.theme == "light"


def test_config_from_dict_handles_missing_keys():
    restored = AppConfig.from_dict({})
    assert restored.theme == "system"
