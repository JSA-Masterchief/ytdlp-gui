# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows build.

Build from the repo root with:  .\\build.ps1
(or directly:  pyinstaller packaging\\ytdlp-gui.spec --noconfirm --clean)

By default this produces ONE self-contained, windowed exe:
dist\\ytdlp-gui.exe. Set YTDLP_GUI_ONEDIR=1 for a one-folder build instead
(dist\\ytdlp-gui\\ytdlp-gui.exe + _internal\\), which starts faster.

FFmpeg: set YTDLP_GUI_FFMPEG_DIR to a folder holding ffmpeg.exe and
ffprobe.exe to embed them, or just place them next to the exe; the app
finds either (see backend/ffmpeg_manager.py).
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is injected by PyInstaller
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from app.constants import APP_NAME, APP_VERSION  # noqa: E402

_ver_parts = [int(p) for p in APP_VERSION.split(".")]
_ver_tuple = tuple((_ver_parts + [0, 0, 0, 0])[:4])

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_ver_tuple, prodvers=_ver_tuple),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("FileDescription", APP_NAME),
                        StringStruct("FileVersion", APP_VERSION),
                        StringStruct("InternalName", "ytdlp-gui"),
                        StringStruct("OriginalFilename", "ytdlp-gui.exe"),
                        StringStruct("ProductName", APP_NAME),
                        StringStruct("ProductVersion", APP_VERSION),
                        StringStruct("LegalCopyright", "MIT License"),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

# The app only uses QtCore/QtGui/QtWidgets; keep the large optional Qt
# modules and dev-only tooling out of the bundle.
EXCLUDES = [
    "tkinter",
    "pytest",
    "pytestqt",
    "PyInstaller",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtSql",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtDesigner",
]

ONEDIR = os.environ.get("YTDLP_GUI_ONEDIR") == "1"

# Record which yt-dlp gets bundled, so the in-app updater can tell whether a
# downloaded yt-dlp is actually newer (see backend/ytdlp_updater.py).
import yt_dlp.version  # noqa: E402

BUILD_DIR = ROOT / "build"
BUILD_DIR.mkdir(exist_ok=True)
bundled_version_file = BUILD_DIR / "ytdlp_bundled_version.txt"
bundled_version_file.write_text(yt_dlp.version.__version__, encoding="utf-8")

extra_binaries = []
ffmpeg_dir = os.environ.get("YTDLP_GUI_FFMPEG_DIR")
if ffmpeg_dir:
    for tool in ("ffmpeg.exe", "ffprobe.exe"):
        tool_path = Path(ffmpeg_dir) / tool
        if not tool_path.is_file():
            raise SystemExit(f"{tool} not found in {ffmpeg_dir}")
        extra_binaries.append((str(tool_path), "."))

a = Analysis(  # noqa: F821
    [str(SRC / "app" / "main.py")],
    pathex=[str(SRC)],
    binaries=extra_binaries,
    datas=[
        (str(ROOT / "assets" / "icon.ico"), "assets"),
        (str(bundled_version_file), "."),
    ],
    hiddenimports=[],  # yt-dlp ships its own PyInstaller hook for its extractors
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

# Qt plugins drag in heavy libraries a Widgets app never loads: the
# virtual-keyboard input plugin pulls in all of Qt Quick/QML, the PDF
# image-format plugin pulls in Qt PDF, and opengl32sw.dll is a ~20 MB
# software OpenGL fallback that QtWidgets doesn't use. Dropping a plugin
# is safe: Qt simply skips plugins that aren't present.
_DROP_BINARIES = (
    "opengl32sw.dll",
    "qt6quick",
    "qt6qml",
    "qt6pdf",
    "qt6virtualkeyboard",
    "qtvirtualkeyboardplugin.dll",
    "qpdf.dll",
)
a.binaries = [
    entry for entry in a.binaries
    if not Path(entry[0]).name.lower().startswith(_DROP_BINARIES)
]

pyz = PYZ(a.pure)  # noqa: F821

_exe_options = dict(
    name="ytdlp-gui",
    icon=str(ROOT / "assets" / "icon.ico"),
    version=version_info,
    console=False,
    upx=False,
    debug=False,
    strip=False,
)

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **_exe_options)  # noqa: F821
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ytdlp-gui")  # noqa: F821
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **_exe_options)  # noqa: F821
