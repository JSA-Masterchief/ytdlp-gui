"""Tests for the in-app yt-dlp updater. Never touches the network or the
real yt_dlp module: downloads go through a fake opener, and activation is
exercised with a throwaway package name."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend import ytdlp_updater as up
from backend.ytdlp_updater import Release, UpdateError

FAKE_PKG = "fake_ytdlp_pkg_for_tests"


# ------------------------------------------------------------------ helpers

class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(routes: dict[str, bytes | Exception]):
    def opener(request, timeout=None):  # noqa: ANN001
        url = request.full_url if hasattr(request, "full_url") else request
        result = routes[url]
        if isinstance(result, Exception):
            raise result
        return _FakeResponse(result)

    return opener


def _wheel(version: str = "2099.1.1", package: str = "yt_dlp", extra: dict[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(f"{package}/__init__.py", "VALUE = 'ok'\n")
        zf.writestr(f"{package}/version.py", f"__version__ = '{version}'\n")
        zf.writestr(f"{package}/extractor/youtube.py", "# extractor\n")
        zf.writestr(f"{package}-{version}.dist-info/METADATA", "Name: yt-dlp\n")
        for name, content in (extra or {}).items():
            zf.writestr(name, content)
    return buffer.getvalue()


def _release(data: bytes, version: str = "2099.1.1", requires_python: str | None = ">=3.9") -> Release:
    return Release(
        version=version,
        wheel_url="https://files.example/yt_dlp.whl",
        sha256=hashlib.sha256(data).hexdigest(),
        requires_python=requires_python,
    )


def _pypi_json(version: str, files: list[dict]) -> bytes:
    return json.dumps({"info": {"version": version, "requires_python": ">=3.9"}, "urls": files}).encode()


@pytest.fixture
def fake_pkg_cleanup():
    before = list(sys.path)
    yield
    sys.path[:] = before
    for name in list(sys.modules):
        if name == FAKE_PKG or name.startswith(FAKE_PKG + "."):
            del sys.modules[name]
    up._override_version = None


def _install_fake_pkg(root: Path, version: str, body: str = "VALUE = 'downloaded'\n") -> Path:
    pkg = root / version / FAKE_PKG
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(body, encoding="utf-8")
    (root / "active").write_text(version, encoding="utf-8")
    return pkg


# ----------------------------------------------------------------- versions

def test_parse_and_compare_calendar_versions():
    assert up.parse_version("2026.08.19") == (2026, 8, 19)
    assert up.parse_version("2026.08.19.1") == (2026, 8, 19, 1)
    assert up.is_newer("2026.09.01", "2026.08.19")
    assert up.is_newer("2026.08.19.1", "2026.08.19")
    assert not up.is_newer("2026.08.19", "2026.08.19")
    assert not up.is_newer("2025.12.31", "2026.01.01")
    assert up.is_newer("2026.01.01", None)
    assert not up.is_newer(None, "2026.01.01")


@pytest.mark.parametrize(
    "spec, python, ok",
    [
        (">=3.9", (3, 12, 4), True),
        (">=3.13", (3, 12, 4), False),
        (">=3.10,<4", (3, 12, 0), True),
        (">=3.10, <3.12", (3, 12, 0), False),
        (None, (3, 12, 0), True),
        ("garbage", (3, 12, 0), True),
    ],
)
def test_python_supported(spec, python, ok):
    assert up.python_supported(spec, python) is ok


# --------------------------------------------------------------- PyPI lookup

def test_fetch_latest_release_picks_the_universal_wheel():
    files = [
        {"packagetype": "sdist", "filename": "yt_dlp-2099.1.1.tar.gz", "url": "https://x/sdist", "digests": {"sha256": "a"}},
        {"packagetype": "bdist_wheel", "filename": "yt_dlp-2099.1.1-py3-none-any.whl",
         "url": "https://x/wheel", "digests": {"sha256": "abc"}, "requires_python": ">=3.10"},
    ]
    opener = _opener({up.PYPI_JSON_URL: _pypi_json("2099.1.1", files)})
    release = up.fetch_latest_release(opener=opener)
    assert release == Release("2099.1.1", "https://x/wheel", "abc", ">=3.10")


def test_fetch_latest_release_network_error_is_friendly():
    opener = _opener({up.PYPI_JSON_URL: OSError("no route to host")})
    with pytest.raises(UpdateError, match="Couldn't reach PyPI"):
        up.fetch_latest_release(opener=opener)


def test_fetch_latest_release_rejects_unexpected_payload():
    opener = _opener({up.PYPI_JSON_URL: b"<html>oops</html>"})
    with pytest.raises(UpdateError):
        up.fetch_latest_release(opener=opener)


def test_fetch_latest_release_without_wheel_fails():
    opener = _opener({up.PYPI_JSON_URL: _pypi_json("2099.1.1", [])})
    with pytest.raises(UpdateError, match="No installable package"):
        up.fetch_latest_release(opener=opener)


# ------------------------------------------------------------------- install

def test_install_extracts_only_the_package_and_marks_it_active(tmp_path):
    data = _wheel(extra={"../evil.py": "boom", "/abs.py": "boom"})
    release = _release(data)
    version = up.install_release(release, root=tmp_path, opener=_opener({release.wheel_url: data}))

    assert version == "2099.1.1"
    assert (tmp_path / "active").read_text() == "2099.1.1"
    installed = tmp_path / "2099.1.1"
    assert (installed / "yt_dlp" / "__init__.py").is_file()
    assert (installed / "yt_dlp" / "extractor" / "youtube.py").is_file()
    assert not (installed / "yt_dlp-2099.1.1.dist-info").exists()
    assert not (tmp_path / "evil.py").exists()
    assert not any(p.name.startswith(".staging") for p in tmp_path.iterdir())
    assert up.installed_version(tmp_path) == "2099.1.1"


def test_install_rejects_checksum_mismatch_and_changes_nothing(tmp_path):
    data = _wheel()
    release = Release("2099.1.1", "https://files.example/yt_dlp.whl", "0" * 64, None)
    with pytest.raises(UpdateError, match="integrity"):
        up.install_release(release, root=tmp_path, opener=_opener({release.wheel_url: data}))
    assert up.installed_version(tmp_path) is None


def test_install_rejects_archive_without_the_package(tmp_path):
    data = _wheel(package="something_else")
    release = _release(data)
    with pytest.raises(UpdateError, match="didn't contain"):
        up.install_release(release, root=tmp_path, opener=_opener({release.wheel_url: data}))
    assert up.installed_version(tmp_path) is None


def test_install_refuses_release_needing_newer_python(tmp_path):
    data = _wheel()
    release = _release(data, requires_python=">=9.0")
    with pytest.raises(UpdateError, match="newer version of this app"):
        up.install_release(release, root=tmp_path, opener=_opener({}))


def test_install_replaces_previous_download(tmp_path):
    first = _wheel("2099.1.1")
    second = _wheel("2099.2.2")
    r1, r2 = _release(first, "2099.1.1"), _release(second, "2099.2.2")
    up.install_release(r1, root=tmp_path, opener=_opener({r1.wheel_url: first}))
    up.install_release(r2, root=tmp_path, opener=_opener({r2.wheel_url: second}))
    assert up.installed_version(tmp_path) == "2099.2.2"


def test_active_marker_cannot_point_outside(tmp_path):
    (tmp_path / "active").write_text("..", encoding="utf-8")
    assert up.installed_version(tmp_path) is None
    (tmp_path / "active").write_text("../../Windows", encoding="utf-8")
    assert up.installed_version(tmp_path) is None


def test_reset_to_bundled_forgets_download(tmp_path):
    data = _wheel()
    release = _release(data)
    up.install_release(release, root=tmp_path, opener=_opener({release.wheel_url: data}))
    up.reset_to_bundled(tmp_path)
    assert up.installed_version(tmp_path) is None


# ---------------------------------------------------------------- activation

def test_activate_uses_newer_download(tmp_path, fake_pkg_cleanup):
    pkg = _install_fake_pkg(tmp_path, "2099.1.1")
    (tmp_path / "2000.1.1").mkdir()  # stale leftover from an older update

    assert up.activate_override(tmp_path, package=FAKE_PKG, bundled="2026.8.19") == "2099.1.1"
    module = sys.modules[FAKE_PKG]
    assert module.VALUE == "downloaded"
    assert Path(module.__file__).parent == pkg
    assert up.override_active()
    assert not (tmp_path / "2000.1.1").exists()


def test_activate_ignores_download_not_newer_than_bundled(tmp_path, fake_pkg_cleanup):
    _install_fake_pkg(tmp_path, "2020.1.1")
    assert up.activate_override(tmp_path, package=FAKE_PKG, bundled="2026.8.19") is None
    assert FAKE_PKG not in sys.modules
    assert up.installed_version(tmp_path) is None  # cleared so it can't shadow the newer bundled copy
    assert not up.override_active()


def test_activate_falls_back_when_download_is_broken(tmp_path, fake_pkg_cleanup):
    _install_fake_pkg(tmp_path, "2099.1.1", body="raise RuntimeError('broken release')\n")
    assert up.activate_override(tmp_path, package=FAKE_PKG, bundled="2026.8.19") is None
    assert FAKE_PKG not in sys.modules
    assert str(tmp_path / "2099.1.1") not in sys.path
    assert up.installed_version(tmp_path) is None


def test_activate_without_download_is_a_no_op(tmp_path, fake_pkg_cleanup):
    assert up.activate_override(tmp_path, package=FAKE_PKG, bundled="2026.8.19") is None


def test_bundled_version_from_source_matches_installed_yt_dlp():
    import yt_dlp.version

    assert up.bundled_version() == yt_dlp.version.__version__


def test_bundled_version_in_frozen_build_reads_version_file(tmp_path):
    (tmp_path / up.BUNDLED_VERSION_FILENAME).write_text("2026.08.19\n", encoding="utf-8")
    with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", str(tmp_path), create=True):
        assert up.bundled_version() == "2026.08.19"


# ------------------------------------------------------------------- service

def test_service_reports_available_update(qtbot):
    from services.ytdlp_update_service import YtdlpUpdateService

    service = YtdlpUpdateService()
    release = Release("2099.1.1", "https://x", "abc", None)
    with patch.object(up, "fetch_latest_release", return_value=release), patch.object(
        service, "pending_version", return_value=None
    ):
        with qtbot.waitSignal(service.check_finished, timeout=3000) as blocker:
            assert service.check()
    assert blocker.args[0] == release
    assert not service.busy


def test_service_reports_up_to_date(qtbot):
    from services.ytdlp_update_service import YtdlpUpdateService

    service = YtdlpUpdateService()
    release = Release("2000.1.1", "https://x", "abc", None)
    with patch.object(up, "fetch_latest_release", return_value=release), patch.object(
        service, "pending_version", return_value=None
    ):
        with qtbot.waitSignal(service.check_finished, timeout=3000) as blocker:
            service.check()
    assert blocker.args[0] is None


def test_service_reports_failure(qtbot):
    from services.ytdlp_update_service import YtdlpUpdateService

    service = YtdlpUpdateService()
    with patch.object(up, "fetch_latest_release", side_effect=UpdateError("offline")):
        with qtbot.waitSignal(service.check_failed, timeout=3000) as blocker:
            service.check()
    assert blocker.args == ["offline"]


def test_service_install(qtbot):
    from services.ytdlp_update_service import YtdlpUpdateService

    service = YtdlpUpdateService()
    release = Release("2099.1.1", "https://x", "abc", None)
    with patch.object(up, "install_release", return_value="2099.1.1"):
        with qtbot.waitSignal(service.install_finished, timeout=3000) as blocker:
            assert service.install(release)
    assert blocker.args == ["2099.1.1"]


# --------------------------------------------------------------- settings UI

def _settings_page(qtbot, tmp_path):
    from app.config import AppConfig
    from backend.ffmpeg_manager import ExecutableStatus
    from ui.pages.settings_page import SettingsPage

    missing = ExecutableStatus(name="ffmpeg", path=None, found=False, error="not found")
    with patch("ui.pages.settings_page.check_ffmpeg", return_value=missing), patch(
        "ui.pages.settings_page.check_ffprobe", return_value=missing
    ):
        page = SettingsPage(AppConfig())
    qtbot.addWidget(page)
    return page


def test_settings_shows_running_version(qtbot, tmp_path):
    import yt_dlp.version

    with patch.object(up, "updates_root", return_value=tmp_path):
        page = _settings_page(qtbot, tmp_path)
    assert yt_dlp.version.__version__ in page.ytdlp_version_label.text()
    assert page.install_update_button.isHidden()


def test_settings_update_flow(qtbot, tmp_path):
    with patch.object(up, "updates_root", return_value=tmp_path):
        page = _settings_page(qtbot, tmp_path)
        release = Release("2099.1.1", "https://x", "abc", None)
        page.show_available_update(release)
        assert not page.install_update_button.isHidden()
        assert "2099.1.1" in page.install_update_button.text()

        with patch.object(page.update_service, "install", return_value=True) as install:
            page.install_update_button.click()
        install.assert_called_once_with(release)

        (tmp_path / "2099.1.1" / "yt_dlp").mkdir(parents=True)
        (tmp_path / "2099.1.1" / "yt_dlp" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "active").write_text("2099.1.1", encoding="utf-8")
        page._on_install_finished("2099.1.1")
        assert "Restart" in page.update_status_label.text()
        assert not page.restart_button.isHidden()

        with qtbot.waitSignal(page.restart_requested, timeout=1000):
            page.restart_button.click()

        page.reset_ytdlp_button.click()
        assert up.installed_version(tmp_path) is None


def test_settings_auto_check_checkbox_round_trips(qtbot, tmp_path):
    page = _settings_page(qtbot, tmp_path)
    assert page.auto_check_updates_checkbox.isChecked()
    page.auto_check_updates_checkbox.setChecked(False)
    assert page.current_config().check_ytdlp_updates is False


def test_config_check_updates_validation():
    from app.config import AppConfig

    assert AppConfig.from_dict({"check_ytdlp_updates": False}).check_ytdlp_updates is False
    assert AppConfig.from_dict({"check_ytdlp_updates": "nope"}).check_ytdlp_updates is True


# --------------------------------------------------------------- main window

def test_startup_check_offers_update_via_toast(qtbot, tmp_path):
    with patch("utils.paths.get_app_data_dir", return_value=tmp_path), patch(
        "app.config.get_app_data_dir", return_value=tmp_path
    ):
        from ui.main_window import MainWindow

        window = MainWindow()
    qtbot.addWidget(window)
    release = Release("2099.1.1", "https://x", "abc", None)
    with patch.object(window.update_service, "check", return_value=True):
        window.check_for_ytdlp_update_quietly()
    with patch.object(window.toast, "show_message") as toast:
        window.update_service.check_finished.emit(release, "2026.08.19")
    toast.assert_called_once()
    assert "2099.1.1" in toast.call_args[0][0]

    # A later manual check from Settings must not toast again.
    with patch.object(window.toast, "show_message") as toast:
        window.update_service.check_finished.emit(release, "2026.08.19")
    toast.assert_not_called()
    window.download_manager.shutdown()


def test_restart_relaunches_the_app(qtbot, tmp_path):
    with patch("utils.paths.get_app_data_dir", return_value=tmp_path), patch(
        "app.config.get_app_data_dir", return_value=tmp_path
    ):
        from ui.main_window import MainWindow

        window = MainWindow()
    qtbot.addWidget(window)
    with patch("ui.main_window.QProcess.startDetached") as start, patch.object(window, "close") as close:
        window.restart_app()
    start.assert_called_once()
    close.assert_called_once()
    window.download_manager.shutdown()
