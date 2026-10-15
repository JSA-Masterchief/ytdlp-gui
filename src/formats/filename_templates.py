"""Filename template presets and validation.

Validation delegates to yt_dlp.YoutubeDL.validate_outtmpl (the same check
yt-dlp itself runs on -o values) rather than a hand-rolled regex, so a
template accepted here is one yt-dlp will actually accept.
"""

from __future__ import annotations

from dataclasses import dataclass

CUSTOM_PRESET_KEY = "custom"

# key -> (display label, template)
FILENAME_TEMPLATE_PRESETS: dict[str, tuple[str, str]] = {
    "title": ("Title", "%(title)s.%(ext)s"),
    "title_id": ("Title + video ID", "%(title)s [%(id)s].%(ext)s"),
    "title_uploader": ("Uploader - Title", "%(uploader)s - %(title)s.%(ext)s"),
    "date_title": ("Upload date - Title", "%(upload_date)s - %(title)s.%(ext)s"),
    "playlist_index_title": ("Playlist index - Title", "%(playlist_index)s - %(title)s.%(ext)s"),
}

# A short reference shown next to the editor, per the "explain available
# template variables" requirement. Not exhaustive — yt-dlp supports many more.
COMMON_TEMPLATE_VARIABLES: dict[str, str] = {
    "title": "Video title",
    "id": "Video ID",
    "uploader": "Channel / uploader name",
    "upload_date": "Upload date (YYYYMMDD)",
    "playlist_index": "Position within a playlist",
    "playlist_title": "Playlist title",
    "ext": "File extension (required)",
    "resolution": "Resolution, e.g. 1920x1080",
}


@dataclass
class TemplateValidation:
    ok: bool
    error_message: str | None = None
    warning_message: str | None = None


def validate_filename_template(template: str) -> TemplateValidation:
    """Validate a yt-dlp output template. A template yt-dlp accepts but
    that lacks %(ext)s is reported as ok with a warning — it's legal, but
    produces extensionless files, which is almost never intended.
    """
    template = template.strip()
    if not template:
        return TemplateValidation(ok=False, error_message="Filename template cannot be empty.")

    import yt_dlp

    error = yt_dlp.YoutubeDL.validate_outtmpl(template)
    if error is not None:
        return TemplateValidation(ok=False, error_message=f"Invalid template: {error}")

    if "%(ext)s" not in template:
        return TemplateValidation(
            ok=True,
            warning_message="This template has no %(ext)s, so downloaded files will have no file extension.",
        )

    return TemplateValidation(ok=True)


def find_matching_preset(template: str) -> str:
    """Return the preset key whose template equals `template`, or
    CUSTOM_PRESET_KEY if none match — used to pre-select the right entry
    in a preset dropdown when loading a saved template.
    """
    for key, (_label, preset_template) in FILENAME_TEMPLATE_PRESETS.items():
        if preset_template == template:
            return key
    return CUSTOM_PRESET_KEY
