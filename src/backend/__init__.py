"""Backend layer: all yt-dlp / FFmpeg interaction goes through this package.

No other part of the application (UI, download manager) should import
yt_dlp directly. This keeps yt-dlp upgrades isolated to one place, as
required by the project architecture.
"""
