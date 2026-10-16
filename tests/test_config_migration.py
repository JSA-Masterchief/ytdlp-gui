"""Tests for app.config migration, validation, and load/save robustness.

Covers the spec's "first launch / corrupted / missing / migration between
versions" requirements. Every load test runs against a real file in a
temp directory — no mocking of the file I/O being tested.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.config import (
    CONFIG_SCHEMA_VERSION,
    AppConfig,
    load_config,
    migrate_config,
    save_config,
)
from app.constants import MAX_CONCURRENT_DOWNLOADS_LIMIT


@pytest.fixture
def config_dir(tmp_path):
    """Point app.config at an isolated directory for the test's duration."""
    with patch("app.config.get_app_data_dir", return_value=tmp_path):
        yield tmp_path


def _write(config_dir: Path, text: str) -> Path:
    path = config_dir / "config.json"
    path.write_text(text, encoding="utf-8")
    return path


class TestMigration:
    def test_unversioned_config_is_treated_as_v0_and_renamed(self):
        raw = {"download_dir": "/old/dir", "concurrent_downloads": 4, "output_template": "%(id)s.%(ext)s"}
        migrated = migrate_config(raw)
        assert migrated["download_directory"] == "/old/dir"
        assert migrated["max_concurrent_downloads"] == 4
        assert migrated["filename_template"] == "%(id)s.%(ext)s"
        assert "download_dir" not in migrated
        assert migrated["schema_version"] == CONFIG_SCHEMA_VERSION

    def test_explicit_v0_is_migrated(self):
        migrated = migrate_config({"schema_version": 0, "download_dir": "/x"})
        assert migrated["download_directory"] == "/x"

    def test_new_style_key_wins_over_stale_legacy_key(self):
        migrated = migrate_config({"download_dir": "/stale", "download_directory": "/current"})
        assert migrated["download_directory"] == "/current"
        assert "download_dir" not in migrated

    def test_current_version_config_passes_through_unchanged(self):
        raw = {"schema_version": CONFIG_SCHEMA_VERSION, "theme": "dark"}
        assert migrate_config(raw) == raw

    def test_newer_schema_than_this_build_is_not_downgraded_or_rejected(self):
        raw = {"schema_version": CONFIG_SCHEMA_VERSION + 5, "theme": "dark", "future_field": 1}
        migrated = migrate_config(raw)
        assert migrated["schema_version"] == CONFIG_SCHEMA_VERSION + 5
        assert migrated["theme"] == "dark"

    def test_migration_does_not_mutate_its_input(self):
        raw = {"download_dir": "/x"}
        migrate_config(raw)
        assert raw == {"download_dir": "/x"}

    @pytest.mark.parametrize("bad_version", ["1", -3, True, None, 1.5])
    def test_nonsense_schema_version_is_treated_as_v0(self, bad_version):
        migrated = migrate_config({"schema_version": bad_version, "download_dir": "/x"})
        assert migrated["download_directory"] == "/x"

    @pytest.mark.parametrize("not_an_object", [[1, 2], None, "text", 42, True])
    def test_non_object_root_raises_value_error(self, not_an_object):
        with pytest.raises(ValueError):
            migrate_config(not_an_object)


class TestSanitization:
    def test_unknown_theme_falls_back_to_default(self):
        assert AppConfig.from_dict({"theme": "neon"}).theme == "system"

    def test_non_string_theme_falls_back(self):
        assert AppConfig.from_dict({"theme": 5}).theme == "system"

    def test_concurrency_wrong_type_falls_back_to_default(self):
        default = AppConfig().max_concurrent_downloads
        assert AppConfig.from_dict({"max_concurrent_downloads": "abc"}).max_concurrent_downloads == default

    def test_concurrency_bool_is_not_accepted_as_an_int(self):
        default = AppConfig().max_concurrent_downloads
        assert AppConfig.from_dict({"max_concurrent_downloads": True}).max_concurrent_downloads == default

    def test_concurrency_below_minimum_is_clamped_to_one(self):
        assert AppConfig.from_dict({"max_concurrent_downloads": 0}).max_concurrent_downloads == 1
        assert AppConfig.from_dict({"max_concurrent_downloads": -7}).max_concurrent_downloads == 1

    def test_concurrency_above_limit_is_clamped(self):
        cfg = AppConfig.from_dict({"max_concurrent_downloads": 9999})
        assert cfg.max_concurrent_downloads == MAX_CONCURRENT_DOWNLOADS_LIMIT

    def test_null_or_blank_download_directory_falls_back(self):
        default = AppConfig().download_directory
        assert AppConfig.from_dict({"download_directory": None}).download_directory == default
        assert AppConfig.from_dict({"download_directory": "   "}).download_directory == default

    def test_blank_filename_template_falls_back(self):
        default = AppConfig().filename_template
        assert AppConfig.from_dict({"filename_template": ""}).filename_template == default

    def test_blank_tool_paths_become_none(self):
        cfg = AppConfig.from_dict({"ffmpeg_path": "   ", "ytdlp_path": ""})
        assert cfg.ffmpeg_path is None
        assert cfg.ytdlp_path is None

    def test_non_string_tool_path_is_dropped(self):
        assert AppConfig.from_dict({"ffmpeg_path": 123}).ffmpeg_path is None

    def test_values_are_stripped(self):
        cfg = AppConfig.from_dict({"download_directory": "  /x/y  ", "filename_template": " %(id)s.%(ext)s "})
        assert cfg.download_directory == "/x/y"
        assert cfg.filename_template == "%(id)s.%(ext)s"

    def test_one_bad_field_does_not_discard_the_good_ones(self):
        cfg = AppConfig.from_dict({"theme": "dark", "max_concurrent_downloads": "lots", "ffmpeg_path": "/usr/bin/ffmpeg"})
        assert cfg.theme == "dark"
        assert cfg.ffmpeg_path == "/usr/bin/ffmpeg"


class TestLoadConfig:
    def test_missing_file_returns_defaults_without_creating_one(self, config_dir):
        cfg = load_config()
        assert cfg == AppConfig()
        assert not (config_dir / "config.json").exists()

    def test_valid_file_loads(self, config_dir):
        _write(config_dir, json.dumps({"schema_version": 1, "theme": "dark", "max_concurrent_downloads": 3}))
        cfg = load_config()
        assert cfg.theme == "dark"
        assert cfg.max_concurrent_downloads == 3

    def test_legacy_file_is_migrated_on_load(self, config_dir):
        _write(config_dir, json.dumps({"download_dir": "/legacy", "concurrent_downloads": 4}))
        cfg = load_config()
        assert cfg.download_directory == "/legacy"
        assert cfg.max_concurrent_downloads == 4
        assert cfg.schema_version == CONFIG_SCHEMA_VERSION

    def test_loading_does_not_rewrite_the_legacy_file(self, config_dir):
        original = json.dumps({"download_dir": "/legacy"})
        path = _write(config_dir, original)
        load_config()
        assert path.read_text(encoding="utf-8") == original

    @pytest.mark.parametrize("text", ["[1, 2, 3]", "null", '"hello"', "42", "true"])
    def test_non_object_json_does_not_crash_and_is_backed_up(self, config_dir, text):
        path = _write(config_dir, text)
        cfg = load_config()
        assert cfg == AppConfig()
        assert not path.exists()
        assert (config_dir / "config.json.corrupt").read_text(encoding="utf-8") == text

    def test_invalid_json_does_not_crash_and_is_backed_up(self, config_dir):
        _write(config_dir, "{not valid json!!")
        assert load_config() == AppConfig()
        assert (config_dir / "config.json.corrupt").exists()

    def test_empty_file_does_not_crash(self, config_dir):
        _write(config_dir, "")
        assert load_config() == AppConfig()

    def test_non_utf8_bytes_do_not_crash(self, config_dir):
        (config_dir / "config.json").write_bytes(b"\xff\xfe\x00garbage")
        assert load_config() == AppConfig()
        assert (config_dir / "config.json.corrupt").exists()

    def test_partially_invalid_file_keeps_valid_fields_and_is_not_backed_up(self, config_dir):
        _write(config_dir, json.dumps({"theme": "dark", "max_concurrent_downloads": "abc"}))
        cfg = load_config()
        assert cfg.theme == "dark"
        assert cfg.max_concurrent_downloads == AppConfig().max_concurrent_downloads
        assert not (config_dir / "config.json.corrupt").exists()

    def test_backup_failure_does_not_crash_loading(self, config_dir):
        _write(config_dir, "[1]")
        with patch("app.config.os.replace", side_effect=OSError("disk says no")):
            assert load_config() == AppConfig()


class TestSaveConfig:
    def test_save_then_load_round_trips(self, config_dir):
        original = AppConfig(
            theme="dark",
            download_directory="/some/dir",
            max_concurrent_downloads=5,
            ffmpeg_path="/usr/bin/ffmpeg",
            filename_template="%(id)s.%(ext)s",
        )
        save_config(original)
        assert load_config() == original

    def test_save_leaves_no_temp_file_behind(self, config_dir):
        save_config(AppConfig())
        assert sorted(p.name for p in config_dir.iterdir()) == ["config.json"]

    def test_save_overwrites_previous_content(self, config_dir):
        save_config(AppConfig(theme="dark"))
        save_config(AppConfig(theme="light"))
        assert load_config().theme == "light"

    def test_saved_file_is_valid_json_object_with_current_schema(self, config_dir):
        save_config(AppConfig())
        data = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
        assert data["schema_version"] == CONFIG_SCHEMA_VERSION

    def test_failed_write_does_not_clobber_existing_config_or_crash(self, config_dir):
        save_config(AppConfig(theme="dark"))
        with patch("app.config.os.replace", side_effect=OSError("boom")):
            save_config(AppConfig(theme="light"))  # must not raise
        assert load_config().theme == "dark"
        assert sorted(p.name for p in config_dir.iterdir()) == ["config.json"]
