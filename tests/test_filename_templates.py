from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from formats.filename_templates import (
    COMMON_TEMPLATE_VARIABLES,
    CUSTOM_PRESET_KEY,
    FILENAME_TEMPLATE_PRESETS,
    find_matching_preset,
    validate_filename_template,
)


class TestPresets:
    @pytest.mark.parametrize("key", list(FILENAME_TEMPLATE_PRESETS))
    def test_every_preset_is_valid_per_yt_dlp(self, key):
        _label, template = FILENAME_TEMPLATE_PRESETS[key]
        result = validate_filename_template(template)
        assert result.ok, f"preset {key!r} rejected: {result.error_message}"
        assert result.warning_message is None

    @pytest.mark.parametrize("key", list(FILENAME_TEMPLATE_PRESETS))
    def test_every_preset_includes_extension(self, key):
        _label, template = FILENAME_TEMPLATE_PRESETS[key]
        assert "%(ext)s" in template

    def test_every_preset_renders_against_a_real_info_dict(self):
        """Not just 'syntactically valid' — actually render each preset
        through yt-dlp's own filename machinery with sample metadata and
        confirm the output looks like what the preset label promises.
        """
        import yt_dlp

        info = {
            "id": "abc123",
            "title": "My Video",
            "uploader": "Some Channel",
            "upload_date": "20240315",
            "playlist_index": 3,
            "ext": "mp4",
            "extractor": "youtube",
        }
        expected = {
            "title": "My Video.mp4",
            "title_id": "My Video [abc123].mp4",
            "title_uploader": "Some Channel - My Video.mp4",
            "date_title": "20240315 - My Video.mp4",
            "playlist_index_title": "3 - My Video.mp4",
        }
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
            for key, (_label, template) in FILENAME_TEMPLATE_PRESETS.items():
                rendered = ydl.prepare_filename(info, outtmpl=template)
                assert rendered == expected[key], f"preset {key!r} rendered {rendered!r}"

    def test_variable_reference_covers_ext(self):
        assert "ext" in COMMON_TEMPLATE_VARIABLES


class TestValidation:
    def test_empty_template_rejected(self):
        result = validate_filename_template("")
        assert result.ok is False
        assert "empty" in result.error_message.lower()

    def test_whitespace_only_rejected(self):
        assert validate_filename_template("   ").ok is False

    def test_valid_template_accepted_without_warning(self):
        result = validate_filename_template("%(title)s [%(id)s].%(ext)s")
        assert result.ok is True
        assert result.warning_message is None

    def test_incomplete_format_key_rejected_with_message(self):
        result = validate_filename_template("%(title")
        assert result.ok is False
        assert result.error_message

    def test_template_without_ext_is_ok_but_warns(self):
        result = validate_filename_template("%(title)s")
        assert result.ok is True
        assert result.warning_message
        assert "extension" in result.warning_message.lower()

    def test_surrounding_whitespace_is_ignored(self):
        assert validate_filename_template("  %(title)s.%(ext)s  ").ok is True


class TestFindMatchingPreset:
    def test_known_preset_template_matches_its_key(self):
        _label, template = FILENAME_TEMPLATE_PRESETS["title_uploader"]
        assert find_matching_preset(template) == "title_uploader"

    def test_unknown_template_is_custom(self):
        assert find_matching_preset("%(id)s/%(title)s.%(ext)s") == CUSTOM_PRESET_KEY

    def test_every_preset_round_trips(self):
        for key, (_label, template) in FILENAME_TEMPLATE_PRESETS.items():
            assert find_matching_preset(template) == key
