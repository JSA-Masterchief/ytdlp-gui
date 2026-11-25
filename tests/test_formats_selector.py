from __future__ import annotations
import sys
from pathlib import Path
import pytest
SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
from formats.selector import (
    FormatSelection, MODE_AUDIO_ONLY, MODE_VIDEO_ONLY,
    build_command_preview, build_format_string, build_ytdlp_options, render_command_preview,
)

class TestBuildFormatString:
    def test_video_audio_best_mp4(self):
        result = build_format_string(FormatSelection(container="mp4"))
        assert "bv*" in result
        assert "[ext=mp4]" in result
        assert "ba[ext=m4a]" in result

    def test_video_audio_with_height_cap(self):
        result = build_format_string(FormatSelection(quality="1080p", container="mp4"))
        assert "[height<=1080]" in result

    def test_video_only(self):
        result = build_format_string(FormatSelection(mode=MODE_VIDEO_ONLY, quality="720p"))
        assert result.startswith("bv*[height<=720]")
        assert "+ba" not in result

    def test_audio_only(self):
        assert build_format_string(FormatSelection(mode=MODE_AUDIO_ONLY)) == "ba/b"

    def test_custom_override_wins(self):
        selection = FormatSelection(custom_format_string='bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]')
        assert build_format_string(selection) == 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]'

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            FormatSelection(mode="not_a_real_mode")

    def test_invalid_quality_raises(self):
        with pytest.raises(ValueError):
            FormatSelection(quality="not_a_real_quality")

class TestBuildYtdlpOptions:
    def test_video_audio_sets_merge_output_format(self):
        options = build_ytdlp_options(FormatSelection(container="mkv"), "/tmp/downloads", "%(title)s.%(ext)s")
        assert options["merge_output_format"] == "mkv"
        assert "postprocessors" not in options

    def test_audio_only_best_has_no_postprocessor(self):
        options = build_ytdlp_options(FormatSelection(mode=MODE_AUDIO_ONLY, audio_format="best"), "/tmp/downloads", "%(title)s.%(ext)s")
        assert "postprocessors" not in options

    def test_audio_only_mp3_adds_extract_audio_postprocessor(self):
        options = build_ytdlp_options(FormatSelection(mode=MODE_AUDIO_ONLY, audio_format="mp3"), "/tmp/downloads", "%(title)s.%(ext)s")
        assert options["postprocessors"] == [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}]

    def test_outtmpl_combines_dir_and_template(self):
        options = build_ytdlp_options(FormatSelection(), "/tmp/downloads", "%(title)s.%(ext)s")
        assert options["outtmpl"].endswith("%(title)s.%(ext)s")
        assert "downloads" in options["outtmpl"]

class TestBuildCommandPreview:
    def test_preview_contains_format_and_url(self):
        preview = build_command_preview("https://www.youtube.com/watch?v=abc123", FormatSelection(container="mp4"), "/tmp/downloads", "%(title)s.%(ext)s")
        assert preview.startswith("yt-dlp -f")
        assert "abc123" in preview
        assert "--merge-output-format mp4" in preview

    def test_preview_shows_placeholder_when_no_url(self):
        preview = build_command_preview("", FormatSelection(), "/tmp/downloads", "%(title)s.%(ext)s")
        assert "<URL>" in preview

    def test_preview_shows_audio_extraction_flags(self):
        preview = build_command_preview("https://example.com/v", FormatSelection(mode=MODE_AUDIO_ONLY, audio_format="flac"), "/tmp/downloads", "%(title)s.%(ext)s")
        assert "--extract-audio" in preview
        assert "--audio-format flac" in preview

    def test_preview_shows_subtitle_and_sponsorblock_flags(self):
        from formats.advanced_options import AdvancedOptions, SponsorBlockOptions, SubtitleOptions
        advanced = AdvancedOptions(
            subtitles=SubtitleOptions(mode="manual", languages=["en"], embed=True),
            sponsorblock=SponsorBlockOptions(enabled=True, action="remove", categories=["sponsor"]),
        )
        preview = build_command_preview("https://example.com/v", FormatSelection(), "/tmp/downloads", "%(title)s.%(ext)s", advanced=advanced)
        assert "--write-subs" in preview
        assert "--sub-langs en" in preview
        assert "--embed-subs" in preview
        assert "--sponsorblock-remove sponsor" in preview

    def test_preview_shows_metadata_and_thumbnail_flags(self):
        from formats.advanced_options import AdvancedOptions, MetadataOptions
        advanced = AdvancedOptions(metadata=MetadataOptions(embed_metadata=True, embed_thumbnail=True))
        preview = build_command_preview("https://example.com/v", FormatSelection(), "/tmp/downloads", "%(title)s.%(ext)s", advanced=advanced)
        assert "--add-metadata" in preview
        assert "--embed-thumbnail" in preview
        assert "--write-thumbnail" in preview

    def test_preview_appends_raw_custom_args_verbatim(self):
        preview = build_command_preview("https://example.com/v", FormatSelection(), "/tmp/downloads", "%(title)s.%(ext)s", raw_custom_args="--limit-rate 500K --proxy http://127.0.0.1:8080")
        assert "--limit-rate 500K --proxy http://127.0.0.1:8080" in preview
        assert preview.index("--limit-rate") < preview.index("-o ")

    def test_render_command_preview_handles_dict_valued_outtmpl(self):
        options = {"format": "best", "outtmpl": {"default": "%(title)s.%(ext)s", "pl_thumbnail": ""}}
        preview = render_command_preview("https://example.com/v", options)
        assert "%(title)s.%(ext)s" in preview
