# yt-dlp GUI

A modern, cross-platform-ready desktop frontend for [yt-dlp](https://github.com/yt-dlp/yt-dlp), built with PySide6.

> **Status:** Early development. See `docs/ROADMAP.md` for progress.

## Why this project?

yt-dlp is extremely powerful but command-line only. This project exposes its
functionality — format selection, playlists, subtitles, SponsorBlock,
post-processing, cookies, and more — through an approachable graphical
interface, while still giving advanced users full access to raw yt-dlp
arguments.

## Features (planned)

- Paste one or many URLs, analyze before downloading
- Rich format selector (resolution, codec, container, audio-only, etc.)
- Real download queue with progress, pause/cancel/retry
- Playlist browsing with per-item selection
- Subtitles, chapters, SponsorBlock, metadata/thumbnail embedding
- Cookie & proxy support
- Persistent history
- Dark / light / system themes
- Advanced mode with custom yt-dlp arguments + live command preview
- Packaged as a standalone Windows `.exe` (no Python required)

## Installation

_Coming soon — see Building from Source below for now._

## Building from source

```bash
git clone https://github.com/<you>/ytdlp-gui.git
cd ytdlp-gui
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
python src/app/main.py
```

## FFmpeg setup

Some format merges, audio extraction, and subtitle embedding require FFmpeg
and FFprobe. The app will detect them automatically if they're on your PATH,
or you can point to them manually in Settings → FFmpeg.

## Disclaimer

This application is a general-purpose frontend for yt-dlp. It does not
implement or facilitate DRM circumvention. Users are solely responsible for
ensuring their use complies with applicable laws, the terms of service of
the sites they download from, and the rights holders of any content.

## License

MIT — see [LICENSE](LICENSE).
