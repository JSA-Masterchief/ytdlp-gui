"""The single point of contact with yt-dlp."""

from __future__ import annotations

import logging
from typing import Any

import yt_dlp

from backend.models import FormatInfo, MediaInfo, PlaylistEntry, PlaylistInfo
from backend.progress import ProgressCallback, make_yt_dlp_hook

logger = logging.getLogger("ytdlp_gui")


class YtdlpBackendError(Exception):
    def __init__(self, user_message: str, technical_detail: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.technical_detail = technical_detail


class DownloadCancelledError(YtdlpBackendError):
    def __init__(self, technical_detail: str = "Cancelled by user") -> None:
        super().__init__("Download cancelled.", technical_detail)


def _translate_error(exc: Exception) -> YtdlpBackendError:
    text = str(exc).lower()

    if "video unavailable" in text:
        return YtdlpBackendError("This video is unavailable.", str(exc))
    if "sign in" in text or "login required" in text:
        return YtdlpBackendError("This content requires you to be logged in.", str(exc))
    if "age" in text and "restrict" in text:
        return YtdlpBackendError("This content is age-restricted and requires authentication.", str(exc))
    if "private video" in text:
        return YtdlpBackendError("This video is private.", str(exc))
    if "unsupported url" in text:
        return YtdlpBackendError("This URL isn't supported.", str(exc))
    if "unable to download webpage" in text or "network" in text or "urlopen error" in text:
        return YtdlpBackendError("Network connection failed.", str(exc))
    return YtdlpBackendError("Something went wrong while contacting yt-dlp.", str(exc))


def _format_from_dict(raw: dict[str, Any]) -> FormatInfo:
    return FormatInfo(
        format_id=raw.get("format_id", ""),
        ext=raw.get("ext", ""),
        resolution=raw.get("resolution") or raw.get("format_note"),
        fps=raw.get("fps"),
        vcodec=raw.get("vcodec"),
        acodec=raw.get("acodec"),
        abr=raw.get("abr"),
        vbr=raw.get("vbr"),
        filesize=raw.get("filesize"),
        filesize_approx=raw.get("filesize_approx"),
        dynamic_range=raw.get("dynamic_range"),
        note=raw.get("format_note"),
    )


class YtdlpBackend:
    def __init__(self, ytdlp_executable_path: str | None = None) -> None:
        self._ytdlp_executable_path = ytdlp_executable_path

    def get_version(self) -> str:
        return yt_dlp.version.__version__

    def analyze(self, url: str) -> MediaInfo | PlaylistInfo:
        base_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }
        try:
            with yt_dlp.YoutubeDL(base_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise _translate_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

        if info is None:
            raise YtdlpBackendError("No information could be retrieved for this URL.")

        if info.get("_type") == "playlist" or "entries" in info:
            return self._playlist_from_info(info)
        return self._media_from_info(info)

    def _media_from_info(self, info: dict[str, Any]) -> MediaInfo:
        raw_formats = info.get("formats") or []
        formats = [_format_from_dict(f) for f in raw_formats]

        subs = info.get("subtitles") or {}
        auto_subs = info.get("automatic_captions") or {}

        return MediaInfo(
            id=info.get("id", ""),
            title=info.get("title", "Untitled"),
            webpage_url=info.get("webpage_url", ""),
            extractor=info.get("extractor", "unknown"),
            duration=info.get("duration"),
            uploader=info.get("uploader"),
            upload_date=info.get("upload_date"),
            view_count=info.get("view_count"),
            description=info.get("description"),
            thumbnail_url=info.get("thumbnail"),
            formats=formats,
            subtitle_languages=list(subs.keys()),
            automatic_caption_languages=list(auto_subs.keys()),
        )

    def _playlist_from_info(self, info: dict[str, Any]) -> PlaylistInfo:
        entries = []
        for idx, entry in enumerate(info.get("entries") or [], start=1):
            if entry is None:
                continue
            entries.append(
                PlaylistEntry(
                    id=entry.get("id", ""),
                    title=entry.get("title", "Untitled"),
                    url=entry.get("url") or entry.get("webpage_url", ""),
                    duration=entry.get("duration"),
                    index=idx,
                )
            )

        return PlaylistInfo(
            id=info.get("id", ""),
            title=info.get("title", "Untitled playlist"),
            uploader=info.get("uploader"),
            webpage_url=info.get("webpage_url", ""),
            entries=entries,
        )

    def download(
        self,
        url: str,
        options: dict[str, Any],
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        opts = dict(options)
        opts.setdefault("quiet", True)
        opts.setdefault("no_warnings", True)

        if progress_callback is not None:
            hooks = opts.get("progress_hooks", [])
            hooks.append(make_yt_dlp_hook(progress_callback))
            opts["progress_hooks"] = hooks

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadCancelled as exc:
            raise DownloadCancelledError(str(exc)) from exc
        except yt_dlp.utils.DownloadError as exc:
            raise _translate_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc
