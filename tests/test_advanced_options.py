"""Tests for formats.advanced_options.

test_real_yt_dlp_accepts_full_combination below constructs an actual
yt_dlp.YoutubeDL with our generated options (skip_download=True, nothing
fetched) to verify every postprocessor key/param shape is genuinely valid,
not just internally consistent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from formats.advanced_options import (
    AdvancedOptions,
    ChapterOptions,
    MetadataOptions,
    SponsorBlockOptions,
    SubtitleOptions,
    apply_advanced_options,
)


def _base_opts() -> dict:
    return {"format": "best", "outtmpl": "/tmp/%(title)s.%(ext)s"}


class TestSubtitleOptions:
    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            SubtitleOptions(mode="not_a_mode")

    def test_none_mode_adds_nothing(self):
        opts = apply_advanced_options(_base_opts(), AdvancedOptions())
        assert "writesubtitles" not in opts
        assert "writeautomaticsub" not in opts
        assert "postprocessors" not in opts

    def test_manual_mode_sets_writesubtitles_only(self):
        advanced = AdvancedOptions(subtitles=SubtitleOptions(mode="manual", languages=["en"]))
        opts = apply_advanced_options(_base_opts(), advanced)
        assert opts["writesubtitles"] is True
        assert "writeautomaticsub" not in opts
        assert opts["subtitleslangs"] == ["en"]

    def test_auto_mode_sets_writeautomaticsub_only(self):
        advanced = AdvancedOptions(subtitles=SubtitleOptions(mode="auto"))
        opts = apply_advanced_options(_base_opts(), advanced)
        assert opts["writeautomaticsub"] is True
        assert "writesubtitles" not in opts

    def test_all_mode_sets_both(self):
        advanced = AdvancedOptions(subtitles=SubtitleOptions(mode="all"))
        opts = apply_advanced_options(_base_opts(), advanced)
        assert opts["writesubtitles"] is True
        assert opts["writeautomaticsub"] is True

    def test_embed_adds_ffmpeg_embed_subtitle_postprocessor(self):
        advanced = AdvancedOptions(subtitles=SubtitleOptions(mode="manual", embed=True))
        opts = apply_advanced_options(_base_opts(), advanced)
        keys = [pp["key"] for pp in opts["postprocessors"]]
        assert "FFmpegEmbedSubtitle" in keys

    def test_no_embed_means_no_postprocessor(self):
        advanced = AdvancedOptions(subtitles=SubtitleOptions(mode="manual", embed=False))
        opts = apply_advanced_options(_base_opts(), advanced)
        assert "postprocessors" not in opts


class TestSponsorBlockOptions:
    def test_invalid_action_raises(self):
        with pytest.raises(ValueError):
            SponsorBlockOptions(action="delete_everything")

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError):
            SponsorBlockOptions(categories=["not_a_real_category"])

    def test_disabled_adds_nothing(self):
        opts = apply_advanced_options(_base_opts(), AdvancedOptions())
        assert "postprocessors" not in opts

    def test_remove_action_adds_sponsorblock_and_modifychapters(self):
        advanced = AdvancedOptions(sponsorblock=SponsorBlockOptions(enabled=True, action="remove", categories=["sponsor"]))
        opts = apply_advanced_options(_base_opts(), advanced)
        keys = [pp["key"] for pp in opts["postprocessors"]]
        assert keys == ["SponsorBlock", "ModifyChapters"]
        modify_pp = next(pp for pp in opts["postprocessors"] if pp["key"] == "ModifyChapters")
        assert modify_pp["remove_sponsor_segments"] == {"sponsor"}

    def test_mark_action_adds_only_sponsorblock(self):
        advanced = AdvancedOptions(sponsorblock=SponsorBlockOptions(enabled=True, action="mark", categories=["sponsor"]))
        opts = apply_advanced_options(_base_opts(), advanced)
        keys = [pp["key"] for pp in opts["postprocessors"]]
        assert keys == ["SponsorBlock"]


class TestChapterAndMetadataOptions:
    def test_embed_chapters_adds_ffmpeg_metadata_with_add_chapters(self):
        advanced = AdvancedOptions(chapters=ChapterOptions(embed_chapters=True))
        opts = apply_advanced_options(_base_opts(), advanced)
        pp = next(p for p in opts["postprocessors"] if p["key"] == "FFmpegMetadata")
        assert pp["add_chapters"] is True
        assert pp["add_metadata"] is False

    def test_split_chapters_adds_split_postprocessor(self):
        advanced = AdvancedOptions(chapters=ChapterOptions(split_chapters=True))
        opts = apply_advanced_options(_base_opts(), advanced)
        keys = [pp["key"] for pp in opts["postprocessors"]]
        assert "FFmpegSplitChapters" in keys

    def test_embed_metadata_adds_ffmpeg_metadata_with_add_metadata(self):
        advanced = AdvancedOptions(metadata=MetadataOptions(embed_metadata=True))
        opts = apply_advanced_options(_base_opts(), advanced)
        pp = next(p for p in opts["postprocessors"] if p["key"] == "FFmpegMetadata")
        assert pp["add_metadata"] is True
        assert pp["add_chapters"] is False

    def test_write_thumbnail_sets_top_level_flag(self):
        advanced = AdvancedOptions(metadata=MetadataOptions(write_thumbnail=True))
        opts = apply_advanced_options(_base_opts(), advanced)
        assert opts["writethumbnail"] is True

    def test_embed_thumbnail_adds_postprocessor_and_forces_write_thumbnail(self):
        advanced = AdvancedOptions(metadata=MetadataOptions(embed_thumbnail=True, write_thumbnail=False))
        opts = apply_advanced_options(_base_opts(), advanced)
        keys = [pp["key"] for pp in opts["postprocessors"]]
        assert "EmbedThumbnail" in keys
        assert opts["writethumbnail"] is True  # forced on so there's something to embed


class TestRealYtDlpAcceptance:
    def test_real_yt_dlp_accepts_full_combination(self):
        """The single most important test in this file: construct an actual
        yt_dlp.YoutubeDL (no network — skip_download=True) with every
        advanced option turned on simultaneously, and confirm yt-dlp's own
        postprocessor factory accepts every key/param without raising.
        """
        import yt_dlp

        advanced = AdvancedOptions(
            subtitles=SubtitleOptions(mode="all", languages=["en", "es"], embed=True),
            sponsorblock=SponsorBlockOptions(enabled=True, action="remove", categories=["sponsor", "intro"]),
            chapters=ChapterOptions(embed_chapters=True, split_chapters=True),
            metadata=MetadataOptions(embed_metadata=True, embed_thumbnail=True, write_thumbnail=True),
        )
        opts = apply_advanced_options(_base_opts(), advanced)
        opts["skip_download"] = True
        opts["quiet"] = True

        with yt_dlp.YoutubeDL(opts) as ydl:
            all_pps = [pp.__class__.__name__ for stage_pps in ydl._pps.values() for pp in stage_pps]

        assert "FFmpegEmbedSubtitlePP" in all_pps
        assert "SponsorBlockPP" in all_pps
        assert "ModifyChaptersPP" in all_pps
        assert "FFmpegSplitChaptersPP" in all_pps
        assert "FFmpegMetadataPP" in all_pps
        assert "EmbedThumbnailPP" in all_pps

    def test_real_yt_dlp_accepts_mark_only_sponsorblock(self):
        import yt_dlp

        advanced = AdvancedOptions(sponsorblock=SponsorBlockOptions(enabled=True, action="mark", categories=["sponsor"]))
        opts = apply_advanced_options(_base_opts(), advanced)
        opts["skip_download"] = True
        opts["quiet"] = True

        with yt_dlp.YoutubeDL(opts) as ydl:
            after_filter_pps = [pp.__class__.__name__ for pp in ydl._pps["after_filter"]]
            all_pps = [pp.__class__.__name__ for stage_pps in ydl._pps.values() for pp in stage_pps]

        assert "SponsorBlockPP" in after_filter_pps
        assert "ModifyChaptersPP" not in all_pps
