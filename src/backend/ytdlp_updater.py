"""Keeps yt-dlp current without rebuilding the app.

The app ships with ("bundles") a copy of yt-dlp, but sites change all the
time and yt-dlp releases fixes every few weeks. yt-dlp is pure Python, so a
newer release can be downloaded from PyPI and loaded in place of the bundled
copy:

* ``install_release()`` downloads the official wheel, verifies its SHA-256
  against PyPI's published digest, and unpacks just the ``yt_dlp`` package
  into ``%APPDATA%/ytdlp-gui/ytdlp-updates/<version>/``. An ``active`` file
  names the version to use. Nothing already loaded is touched, so the new
  version takes effect on the next start.
* ``activate_override()`` runs at startup *before anything imports yt_dlp*.
  It puts the downloaded copy first on ``sys.path`` only if it is newer than
  the bundled one (so updating the app itself never gets shadowed by an older
  download), and falls back to the bundled copy if it fails to import.

Everything here is network/filesystem plumbing with injectable inputs so it
can be tested without touching the real yt_dlp module or the internet.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import io
import json
import logging
import re
import shutil
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

logger = logging.getLogger("ytdlp_gui")

PACKAGE = "yt_dlp"
PYPI_JSON_URL = "https://pypi.org/pypi/yt-dlp/json"
UPDATES_DIRNAME = "ytdlp-updates"
ACTIVE_FILENAME = "active"
BUNDLED_VERSION_FILENAME = "ytdlp_bundled_version.txt"
MAX_WHEEL_BYTES = 60 * 1024 * 1024
USER_AGENT = "ytdlp-gui-updater"

# Set by activate_override(); read by the Settings page.
_override_version: str | None = None


class UpdateError(Exception):
    """A user-presentable failure while checking for or installing an update."""


@dataclass(frozen=True)
class Release:
    version: str
    wheel_url: str
    sha256: str
    requires_python: str | None = None


# ------------------------------------------------------------------ versions

def parse_version(version: str) -> tuple[int, ...]:
    """yt-dlp uses calendar versions like 2026.08.19 or 2026.08.19.1."""
    parts: list[int] = []
    for piece in str(version).strip().split("."):
        match = re.match(r"\d+", piece)
        if not match:
            break
        parts.append(int(match.group()))
    return tuple(parts)


def is_newer(candidate: str | None, current: str | None) -> bool:
    if not candidate:
        return False
    if not current:
        return True
    return parse_version(candidate) > parse_version(current)


def python_supported(requires_python: str | None, python_version: tuple[int, ...] | None = None) -> bool:
    """Evaluate a PEP 440 ``Requires-Python`` string like ">=3.10" for the
    running interpreter. Clauses we can't parse are treated as satisfied."""
    if not requires_python:
        return True
    current = python_version or sys.version_info[:3]
    for clause in requires_python.split(","):
        match = re.match(r"\s*(>=|<=|==|!=|>|<|~=)\s*([\d.]+)", clause)
        if not match:
            continue
        op, raw = match.groups()
        wanted = parse_version(raw)
        have = tuple(current[: len(wanted)])
        ok = {
            ">=": have >= wanted,
            ">": have > wanted,
            "<=": have <= wanted,
            "<": have < wanted,
            "==": have == wanted,
            "!=": have != wanted,
            "~=": have >= wanted,
        }[op]
        if not ok:
            return False
    return True


# ----------------------------------------------------------------- locations

def updates_root() -> Path:
    from utils.paths import get_app_data_dir

    return get_app_data_dir() / UPDATES_DIRNAME


def _read_active(root: Path) -> str | None:
    try:
        name = (root / ACTIVE_FILENAME).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    # The active marker names a sibling folder; never let it point elsewhere.
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return None
    return name


def installed_version(root: Path | None = None) -> str | None:
    """The downloaded version that will be used on next start, if any."""
    root = root or updates_root()
    name = _read_active(root)
    if name and (root / name / PACKAGE / "__init__.py").is_file():
        return name
    return None


def bundled_version() -> str | None:
    """The yt-dlp version shipped inside this build, read without importing it."""
    if getattr(sys, "frozen", False):
        from utils.paths import get_resource_path

        try:
            return get_resource_path(BUNDLED_VERSION_FILENAME).read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    spec = importlib.util.find_spec(PACKAGE)
    if spec is None or not spec.submodule_search_locations:
        return None
    for location in spec.submodule_search_locations:
        version_file = Path(location) / "version.py"
        if version_file.is_file():
            match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", version_file.read_text(encoding="utf-8"))
            if match:
                return match.group(1)
    return None


def running_version() -> str:
    """The yt-dlp version actually loaded in this process."""
    from yt_dlp.version import __version__

    return __version__


def override_active() -> bool:
    return _override_version is not None


# ---------------------------------------------------------------- activation

def _purge_modules(package: str) -> None:
    for name in list(sys.modules):
        if name == package or name.startswith(package + "."):
            del sys.modules[name]


def _cleanup_stale(root: Path, keep: str | None) -> None:
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.is_dir() and entry.name != keep:
            shutil.rmtree(entry, ignore_errors=True)


def activate_override(
    root: Path | None = None,
    package: str = PACKAGE,
    bundled: str | None = None,
) -> str | None:
    """Make a downloaded yt-dlp importable ahead of the bundled one.

    Must run before anything imports ``package``. Returns the version now in
    use from the download, or None when the bundled copy stays in charge.
    """
    global _override_version
    root = root or updates_root()
    name = _read_active(root)
    if name is None:
        return None
    candidate = root / name
    if not (candidate / package / "__init__.py").is_file():
        return None

    bundled = bundled if bundled is not None else bundled_version()
    if not is_newer(name, bundled):
        logger.info("Downloaded yt-dlp %s is not newer than bundled %s; removing it.", name, bundled)
        reset_to_bundled(root)
        return None

    path_entry = str(candidate)
    sys.path.insert(0, path_entry)
    try:
        module = importlib.import_module(package)
        loaded_from = Path(module.__file__).resolve().parent.parent
        if loaded_from != candidate.resolve():
            raise ImportError(f"{package} was loaded from {loaded_from}, not the downloaded copy")
    except Exception as exc:  # noqa: BLE001 - any failure means: fall back
        logger.warning("Downloaded yt-dlp %s failed to load (%s); using the bundled version.", name, exc)
        if path_entry in sys.path:
            sys.path.remove(path_entry)
        _purge_modules(package)
        reset_to_bundled(root)
        return None

    _cleanup_stale(root, keep=name)
    _override_version = name
    logger.info("Using downloaded yt-dlp %s (bundled: %s)", name, bundled)
    return name


def reset_to_bundled(root: Path | None = None) -> None:
    """Forget any downloaded version; the bundled one is used from next start."""
    root = root or updates_root()
    try:
        (root / ACTIVE_FILENAME).unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------- check / install

Opener = Callable[..., object]


def _http_get(url: str, opener: Opener, timeout: float, limit: int) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=timeout) as response:
            data = response.read(limit + 1)
    except OSError as exc:  # URLError, timeouts, SSL errors are all OSErrors
        raise UpdateError(f"Couldn't reach PyPI: {getattr(exc, 'reason', exc)}") from exc
    if len(data) > limit:
        raise UpdateError("The download was unexpectedly large; aborting.")
    return data


def fetch_latest_release(opener: Opener = urlopen, timeout: float = 15) -> Release:
    raw = _http_get(PYPI_JSON_URL, opener, timeout, limit=8 * 1024 * 1024)
    try:
        payload = json.loads(raw)
        info = payload["info"]
        version = info["version"]
        files = payload["urls"]
    except (ValueError, KeyError, TypeError) as exc:
        raise UpdateError("PyPI returned an unexpected response.") from exc

    for file_info in files:
        if file_info.get("packagetype") == "bdist_wheel" and file_info.get("filename", "").endswith("py3-none-any.whl"):
            sha256 = (file_info.get("digests") or {}).get("sha256")
            url = file_info.get("url", "")
            if sha256 and url.startswith("https://"):
                return Release(
                    version=version,
                    wheel_url=url,
                    sha256=sha256,
                    requires_python=file_info.get("requires_python") or info.get("requires_python"),
                )
    raise UpdateError(f"No installable package found for yt-dlp {version}.")


def _safe_member(name: str, package: str) -> PurePosixPath | None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != package:
        return None
    return path


def install_release(
    release: Release,
    root: Path | None = None,
    opener: Opener = urlopen,
    timeout: float = 60,
    package: str = PACKAGE,
) -> str:
    """Download, verify and unpack `release`, and mark it active for the next start."""
    if not python_supported(release.requires_python):
        raise UpdateError(
            f"yt-dlp {release.version} needs Python {release.requires_python}; "
            "download a newer version of this app instead."
        )
    root = root or updates_root()
    data = _http_get(release.wheel_url, opener, timeout, limit=MAX_WHEEL_BYTES)
    digest = hashlib.sha256(data).hexdigest()
    if digest.lower() != release.sha256.lower():
        raise UpdateError("The downloaded file failed its integrity check; nothing was changed.")

    root.mkdir(parents=True, exist_ok=True)
    staging = root / f".staging-{release.version}"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as wheel:
            members = [(m, _safe_member(m.filename, package)) for m in wheel.infolist()]
            wanted = [(m, p) for m, p in members if p is not None and not m.is_dir()]
            if not wanted:
                raise UpdateError("The download didn't contain yt-dlp.")
            for member, rel_path in wanted:
                target = staging.joinpath(*rel_path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with wheel.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError("The downloaded file was corrupt; nothing was changed.") from exc
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError(f"Couldn't save the update: {exc}") from exc

    if not (staging / package / "__init__.py").is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError("The download didn't contain yt-dlp.")

    final = root / release.version
    if final.exists() and final.resolve() != (root / (installed_version(root) or "")).resolve():
        shutil.rmtree(final, ignore_errors=True)
    if final.exists():
        # The same version is already installed and active; keep it.
        shutil.rmtree(staging, ignore_errors=True)
    else:
        staging.rename(final)

    tmp_marker = root / (ACTIVE_FILENAME + ".tmp")
    tmp_marker.write_text(release.version, encoding="utf-8")
    tmp_marker.replace(root / ACTIVE_FILENAME)
    logger.info("Installed yt-dlp %s to %s (active from next start)", release.version, final)
    return release.version
