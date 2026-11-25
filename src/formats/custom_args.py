"""Parses free-form custom yt-dlp CLI arguments into a real yt-dlp options
dict, using yt-dlp's own argument parser rather than a hand-rolled one —
so whatever is valid on the yt-dlp command line is valid here, and
whatever yt-dlp itself would reject is rejected here too.
"""

from __future__ import annotations

import optparse
import shlex
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CustomArgsResult:
    ok: bool
    overrides: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    urls_in_args: list[str] = field(default_factory=list)


_baseline_cache: dict[str, Any] | None = None


def _baseline_options() -> dict[str, Any]:
    global _baseline_cache
    if _baseline_cache is None:
        from yt_dlp import parse_options

        _, _, _, ydl_opts = parse_options([])
        _baseline_cache = ydl_opts
    return _baseline_cache


def parse_custom_args(raw_text: str) -> CustomArgsResult:
    raw_text = raw_text.strip()
    if not raw_text:
        return CustomArgsResult(ok=True)

    try:
        argv = shlex.split(raw_text)
    except ValueError as exc:
        return CustomArgsResult(ok=False, error_message=f"Could not parse arguments: {exc}")

    from yt_dlp import parse_options

    try:
        _parser, _opts, urls, ydl_opts = parse_options(argv)
    except optparse.OptParseError as exc:
        return CustomArgsResult(ok=False, error_message=str(exc).strip())
    except SystemExit:
        return CustomArgsResult(
            ok=False,
            error_message="This argument isn't usable here (e.g. --help or --version).",
        )

    baseline = _baseline_options()
    overrides = {key: value for key, value in ydl_opts.items() if key not in baseline or baseline[key] != value}

    return CustomArgsResult(ok=True, overrides=overrides, urls_in_args=list(urls))


def merge_custom_args(
    base_options: dict[str, Any], overrides: dict[str, Any]
) -> tuple[dict[str, Any], list[str], set[str]]:
    """Returns (merged_options, conflict_descriptions, conflicting_keys)."""
    merged = dict(base_options)
    conflicts: list[str] = []
    conflicting_keys: set[str] = set()
    baseline_pps = _baseline_options().get("postprocessors", [])

    for key, value in overrides.items():
        if key == "postprocessors":
            genuinely_new = [pp for pp in value if pp not in baseline_pps]
            if genuinely_new:
                merged["postprocessors"] = list(merged.get("postprocessors", [])) + genuinely_new
            continue

        if key == "outtmpl":
            custom_default = value.get("default") if isinstance(value, dict) else None
            existing_template = merged.get("outtmpl")
            if custom_default is not None:
                if existing_template and existing_template != custom_default:
                    conflicts.append(
                        f"Output filename template: GUI set {existing_template!r}, "
                        f"custom arguments override to {custom_default!r}"
                    )
                    conflicting_keys.add("outtmpl")
                merged["outtmpl"] = custom_default
            other_keys = {k: v for k, v in value.items() if k != "default"}
            if other_keys:
                current = merged.get("outtmpl")
                if isinstance(current, str):
                    merged["outtmpl"] = {"default": current, **other_keys}
                else:
                    merged["outtmpl"] = {**(current or {}), **other_keys}
            continue

        if key in merged and merged[key] != value:
            conflicts.append(f"{key}: GUI set {merged[key]!r}, custom arguments override to {value!r}")
            conflicting_keys.add(key)
        merged[key] = value

    return merged, conflicts, conflicting_keys
