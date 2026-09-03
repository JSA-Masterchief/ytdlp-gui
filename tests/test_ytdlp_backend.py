"""Tests for backend.ytdlp_backend.

These mock yt_dlp.YoutubeDL entirely — no real network requests are made,
per project testing requirements.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.models import MediaInfo, PlaylistInfo
from backend.progress import parse_progress_hook
from backend.ytdlp_backend import YtdlpBackend, YtdlpBackendError, _translate_error

SAMPLE_VIDEO_INFO = {
    "_type": "video",
    "id": "r7B6VXeJ3Zs",
    "title": "Sample Video",
    "webpage_url": "https://www.youtube.com/watch?v=r7B6VXeJ3Zs",
    "extractor": "youtube",
    "duration": 212.0,
    "uploader": "Some Channel",
    "upload_date": "20240101",
    "view_count": 1000,
    "description": "A sample description.",
    "thumbnail": "https://example.com/thumb.jpg",
    "subtitles": {"en": [{"ext": "vtt", "url": "https://example.com/en.vtt"}]},
    "automatic_captions": {"en": [], "fr": []},
    "formats": [
        {
            "format_id": "137",
            "ext": "mp4",
            "resolution": "1920x1080",
            "fps": 30,
            "vcodec": "avc1.640028",
            "acodec": "none",
            "filesize": 123456789,
            "format_note": "1080p",
        },
        {
            "format_id": "140",
            "ext": "m4a",
            "resolution": None,
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "abr": 128.0,
            "filesize": 3456789,
            "format_note": "medium",
        },
    ],
}

SAMPLE_PLAYLIST_INFO = {
    "_type": "playlist",
    "id": "PL123",
    "title": "Sample Playlist",
    "uploader": "Some Channel",
    "webpage_url": "https://www.youtube.com/playlist?list=PL123",
    "entries": [
        {"id": "vid1", "title": "First video", "url": "https://youtu.be/vid1", "duration": 100.0},
        None,  # yt-dlp can yield None for unavailable entries
        {"id": "vid2", "title": "Second video", "url": "https://youtu.be/vid2", "duration": 200.0},
    ],
}


@pytest.fixture
def backend() -> YtdlpBackend:
    return YtdlpBackend()


def _mock_ydl(info: dict):
    mock_instance = MagicMock()
    mock_instance.extract_info.return_value = info
    mock_instance.__enter__.return_value = mock_instance
    mock_instance.__exit__.return_value = False
    return mock_instance


class TestAnalyze:
    def test_analyze_single_video_returns_media_info(self, backend: YtdlpBackend):
        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", return_value=_mock_ydl(SAMPLE_VIDEO_INFO)):
            result = backend.analyze("https://www.youtube.com/watch?v=r7B6VXeJ3Zs")

        assert isinstance(result, MediaInfo)
        assert result.id == "r7B6VXeJ3Zs"
        assert result.title == "Sample Video"
        assert len(result.formats) == 2
        assert result.formats[0].is_video_only
        assert result.formats[1].is_audio_only
        assert "en" in result.subtitle_languages
        assert set(result.automatic_caption_languages) == {"en", "fr"}

    def test_analyze_playlist_returns_playlist_info_and_skips_none_entries(self, backend: YtdlpBackend):
        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", return_value=_mock_ydl(SAMPLE_PLAYLIST_INFO)):
            result = backend.analyze("https://www.youtube.com/playlist?list=PL123")

        assert isinstance(result, PlaylistInfo)
        assert result.entry_count == 2  # the None entry must be skipped
        assert result.entries[0].title == "First video"
        assert result.entries[1].title == "Second video"

    def test_analyze_raises_friendly_error_when_info_is_none(self, backend: YtdlpBackend):
        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", return_value=_mock_ydl(None)):
            with pytest.raises(YtdlpBackendError):
                backend.analyze("https://example.com/missing")


class TestErrorTranslation:
    @pytest.mark.parametrize(
        "raw_message,expected_fragment",
        [
            ("ERROR: Video unavailable", "unavailable"),
            ("ERROR: Sign in to confirm your age", "logged in"),
            ("This video is age restricted", "age-restricted"),
            ("Private video", "private"),
            ("Unsupported URL: foo", "supported"),
            ("Unable to download webpage: timed out", "Network"),
        ],
    )
    def test_translate_error_produces_friendly_message(self, raw_message, expected_fragment):
        err = _translate_error(Exception(raw_message))
        assert expected_fragment.lower() in err.user_message.lower()
        # Technical detail must still be preserved for the "Advanced Details" panel.
        assert raw_message in err.technical_detail


class TestProgressParsing:
    def test_percent_is_derived_from_bytes(self):
        progress = parse_progress_hook(
            {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 200, "speed": 1000.0, "eta": 10}
        )
        assert progress.percent == 25.0
        assert progress.status == "downloading"

    def test_finished_status(self):
        progress = parse_progress_hook({"status": "finished", "filename": "video.mp4"})
        assert progress.is_finished
        assert progress.filename == "video.mp4"

    def test_missing_totals_leave_percent_none(self):
        progress = parse_progress_hook({"status": "downloading", "downloaded_bytes": 500})
        assert progress.percent is None
