"""Lightweight URL validation."""

from __future__ import annotations

from urllib.parse import urlparse


def is_valid_url(candidate: str) -> bool:
    candidate = candidate.strip()
    if not candidate:
        return False
    try:
        result = urlparse(candidate)
    except ValueError:
        return False
    return result.scheme in ("http", "https") and bool(result.netloc)


def split_urls(text: str) -> list[str]:
    candidates = [line.strip() for line in text.splitlines()]
    urls = [c for c in candidates if c]
    return urls


def validate_urls(text: str) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    for candidate in split_urls(text):
        if is_valid_url(candidate):
            valid.append(candidate)
        else:
            invalid.append(candidate)
    return valid, invalid
