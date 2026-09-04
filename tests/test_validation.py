from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from utils.validation import is_valid_url, split_urls, validate_urls


def test_valid_https_url():
    assert is_valid_url("https://www.youtube.com/watch?v=r7B6VXeJ3Zs")


def test_valid_http_url():
    assert is_valid_url("http://example.com/video")


def test_rejects_empty_string():
    assert not is_valid_url("")
    assert not is_valid_url("   ")


def test_rejects_missing_scheme():
    assert not is_valid_url("www.youtube.com/watch?v=abc")


def test_rejects_non_url_text():
    assert not is_valid_url("just some random text")


def test_split_urls_handles_multiline_and_blank_lines():
    text = "https://a.com/1\n\nhttps://b.com/2\n  \nhttps://c.com/3"
    result = split_urls(text)
    assert result == ["https://a.com/1", "https://b.com/2", "https://c.com/3"]


def test_validate_urls_separates_valid_and_invalid():
    text = "https://good.com/1\nnot a url\nhttps://good.com/2"
    valid, invalid = validate_urls(text)
    assert valid == ["https://good.com/1", "https://good.com/2"]
    assert invalid == ["not a url"]
