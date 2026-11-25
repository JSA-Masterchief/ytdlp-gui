from __future__ import annotations
import sys
from pathlib import Path
SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
from formats.custom_args import merge_custom_args, parse_custom_args

class TestParseCustomArgs:
    def test_empty_string_is_ok_with_no_overrides(self):
        result = parse_custom_args("")
        assert result.ok is True
        assert result.overrides == {}

    def test_whitespace_only_is_ok_with_no_overrides(self):
        result = parse_custom_args("   \n  ")
        assert result.ok is True
        assert result.overrides == {}

    def test_valid_single_flag(self):
        result = parse_custom_args("--limit-rate 500K")
        assert result.ok is True
        assert result.overrides.get("ratelimit") == 512000

    def test_valid_multiple_flags(self):
        result = parse_custom_args("--limit-rate 1M --proxy http://127.0.0.1:8080 --write-subs")
        assert result.ok is True
        assert result.overrides.get("ratelimit") == 1024 * 1024
        assert result.overrides.get("proxy") == "http://127.0.0.1:8080"
        assert result.overrides.get("writesubtitles") is True

    def test_unrelated_defaults_are_not_reported_as_overrides(self):
        result = parse_custom_args("--limit-rate 500K")
        assert "format" not in result.overrides
        assert "writesubtitles" not in result.overrides

    def test_unknown_flag_returns_friendly_error_not_an_exception(self):
        result = parse_custom_args("--this-is-not-a-real-flag")
        assert result.ok is False
        assert result.error_message
        assert "not-a-real-flag" in result.error_message or "no such option" in result.error_message.lower()

    def test_malformed_quoting_returns_friendly_error(self):
        result = parse_custom_args('--user-agent "unterminated')
        assert result.ok is False
        assert result.error_message

    def test_help_and_version_flags_are_rejected_gracefully(self):
        for flag in ("--version", "--help"):
            result = parse_custom_args(flag)
            assert result.ok is False
            assert result.error_message

    def test_urls_typed_into_custom_args_are_surfaced(self):
        result = parse_custom_args("https://example.com/video --limit-rate 500K")
        assert result.ok is True
        assert "https://example.com/video" in result.urls_in_args

    def test_no_urls_when_none_typed(self):
        result = parse_custom_args("--limit-rate 500K")
        assert result.urls_in_args == []

    def test_postprocessor_flag_produces_postprocessors_override(self):
        result = parse_custom_args("--embed-thumbnail")
        assert result.ok is True
        assert "postprocessors" in result.overrides
        assert "EmbedThumbnail" in [pp["key"] for pp in result.overrides["postprocessors"]]

    def test_output_template_flag_produces_outtmpl_override(self):
        result = parse_custom_args('-o "%(uploader)s/%(title)s.%(ext)s"')
        assert result.ok is True
        assert result.overrides["outtmpl"]["default"] == "%(uploader)s/%(title)s.%(ext)s"

class TestMergeCustomArgs:
    def test_no_overrides_leaves_base_untouched(self):
        base = {"format": "best", "outtmpl": "/tmp/%(title)s.%(ext)s"}
        merged, conflicts, conflicting_keys = merge_custom_args(base, {})
        assert merged == base
        assert conflicts == []

    def test_new_scalar_key_added_without_conflict(self):
        merged, conflicts, conflicting_keys = merge_custom_args({"format": "best"}, {"ratelimit": 500_000})
        assert merged["ratelimit"] == 500_000
        assert conflicts == []

    def test_conflicting_scalar_key_is_overridden_and_reported(self):
        merged, conflicts, conflicting_keys = merge_custom_args({"format": "bv*+ba/b"}, {"format": "worst"})
        assert merged["format"] == "worst"
        assert len(conflicts) == 1
        assert "format" in conflicts[0]
        assert conflicting_keys == {"format"}

    def test_postprocessors_are_appended_not_replaced(self):
        base = {"postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}]}
        result = parse_custom_args("--embed-thumbnail")
        merged, conflicts, conflicting_keys = merge_custom_args(base, result.overrides)
        keys = [pp["key"] for pp in merged["postprocessors"]]
        assert "FFmpegExtractAudio" in keys
        assert "EmbedThumbnail" in keys
        assert conflicts == []

    def test_baseline_noise_postprocessor_is_not_duplicated_in(self):
        base = {"postprocessors": []}
        result = parse_custom_args("--limit-rate 500K")
        merged, conflicts, conflicting_keys = merge_custom_args(base, result.overrides)
        assert merged.get("postprocessors", []) == []

    def test_outtmpl_override_conflicts_and_wins(self):
        base = {"outtmpl": "/tmp/%(title)s.%(ext)s"}
        result = parse_custom_args('-o "%(uploader)s/%(title)s.%(ext)s"')
        merged, conflicts, conflicting_keys = merge_custom_args(base, result.overrides)
        assert merged["outtmpl"] == "%(uploader)s/%(title)s.%(ext)s"
        assert len(conflicts) == 1
        assert "Output filename template" in conflicts[0]

    def test_outtmpl_side_effect_key_does_not_conflict_with_gui_template(self):
        base = {"outtmpl": "/tmp/%(title)s.%(ext)s"}
        result = parse_custom_args("--embed-thumbnail")
        merged, conflicts, conflicting_keys = merge_custom_args(base, result.overrides)
        assert merged["outtmpl"]["default"] == "/tmp/%(title)s.%(ext)s"
        assert "pl_thumbnail" in merged["outtmpl"]
        assert conflicts == []

    def test_real_end_to_end_combination_produces_valid_yt_dlp_options(self):
        import yt_dlp
        base = {
            "format": "bv*[height<=1080]+ba/b",
            "outtmpl": "/tmp/%(title)s.%(ext)s",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}],
        }
        result = parse_custom_args("--limit-rate 500K --embed-thumbnail --write-subs --sub-langs en")
        assert result.ok is True
        merged, conflicts, conflicting_keys = merge_custom_args(base, result.overrides)
        merged["skip_download"] = True
        merged["quiet"] = True
        with yt_dlp.YoutubeDL(merged) as ydl:
            pp_keys = [pp.__class__.__name__ for stage in ydl._pps.values() for pp in stage]
        assert "FFmpegExtractAudioPP" in pp_keys
        assert "EmbedThumbnailPP" in pp_keys
