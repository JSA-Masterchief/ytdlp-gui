from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from formats.selector import (
    FormatSelection,
    MODE_AUDIO_ONLY,
    MODE_VIDEO_ONLY,
    build_command_preview,
    build_format_string,
    build_ytdlp_options,
)


class TestBuildFormatString:
    def test_video_audio_best_mp4(self):
        selection = FormatSelection(container="mp4")
        result = build_format_string(selection)
        assert "bv*" in result
        assert "[ext=mp4]" in result
        assert "ba[ext=m4a]" in result

    def test_video_audio_with_height_cap(self):
        selection = FormatSelection(quality="1080p", container="mp4")
        result = build_format_string(selection)
        assert "[height<=1080]" in result

    def test_video_only(self):
        selection = FormatSelection(mode=MODE_VIDEO_ONLY, quality="720p")
        result = build_format_string(selection)
        assert result.startswith("bv*[height<=720]")
        assert "+ba" not in result

    def test_audio_only(self):
        selection = FormatSelection(mode=MODE_AUDIO_ONLY)
        assert build_format_string(selection) == "ba/b"

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
        selection = FormatSelection(container="mkv")
        options = build_ytdlp_options(selection, "/tmp/downloads", "%(title)s.%(ext)s")
        assert options["merge_output_format"] == "mkv"
        assert "postprocessors" not in options

    def test_audio_only_best_has_no_postprocessor(self):
        selection = FormatSelection(mode=MODE_AUDIO_ONLY, audio_format="best")
        options = build_ytdlp_options(selection, "/tmp/downloads", "%(title)s.%(ext)s")
        assert "postprocessors" not in options

    def test_audio_only_mp3_adds_extract_audio_postprocessor(self):
        selection = FormatSelection(mode=MODE_AUDIO_ONLY, audio_format="mp3")
        options = build_ytdlp_options(selection, "/tmp/downloads", "%(title)s.%(ext)s")
        assert options["postprocessors"] == [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}
        ]

    def test_outtmpl_combines_dir_and_template(self):
        selection = FormatSelection()
        options = build_ytdlp_options(selection, "/tmp/downloads", "%(title)s.%(ext)s")
        assert options["outtmpl"].endswith("%(title)s.%(ext)s")
        assert "downloads" in options["outtmpl"]


class TestBuildCommandPreview:
    def test_preview_contains_format_and_url(self):
        selection = FormatSelection(container="mp4")
        preview = build_command_preview(
            "https://www.youtube.com/watch?v=abc123", selection, "/tmp/downloads", "%(title)s.%(ext)s"
        )
        assert preview.startswith("yt-dlp -f")
        assert "abc123" in preview
        assert "--merge-output-format mp4" in preview

    def test_preview_shows_placeholder_when_no_url(self):
        selection = FormatSelection()
        preview = build_command_preview("", selection, "/tmp/downloads", "%(title)s.%(ext)s")
        assert "<URL>" in preview

    def test_preview_shows_audio_extraction_flags(self):
        selection = FormatSelection(mode=MODE_AUDIO_ONLY, audio_format="flac")
        preview = build_command_preview(
            "https://example.com/v", selection, "/tmp/downloads", "%(title)s.%(ext)s"
        )
        assert "--extract-audio" in preview
        assert "--audio-format flac" in preview

    def test_preview_shows_subtitle_and_sponsorblock_flags(self):
        from formats.advanced_options import AdvancedOptions, SponsorBlockOptions, SubtitleOptions

        selection = FormatSelection()
        advanced = AdvancedOptions(
            subtitles=SubtitleOptions(mode="manual", languages=["en"], embed=True),
            sponsorblock=SponsorBlockOptions(enabled=True, action="remove", categories=["sponsor"]),
        )
        preview = build_command_preview(
            "https://example.com/v", selection, "/tmp/downloads", "%(title)s.%(ext)s", advanced=advanced
        )
        assert "--write-subs" in preview
        assert "--sub-langs en" in preview
        assert "--embed-subs" in preview
        assert "--sponsorblock-remove sponsor" in preview

    def test_preview_shows_metadata_and_thumbnail_flags(self):
        from formats.advanced_options import AdvancedOptions, MetadataOptions

        selection = FormatSelection()
        advanced = AdvancedOptions(metadata=MetadataOptions(embed_metadata=True, embed_thumbnail=True))
        preview = build_command_preview(
            "https://example.com/v", selection, "/tmp/downloads", "%(title)s.%(ext)s", advanced=advanced
        )
        assert "--add-metadata" in preview
        assert "--embed-thumbnail" in preview
        assert "--write-thumbnail" in preview
