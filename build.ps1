<#
.SYNOPSIS
    Builds the Windows release of yt-dlp GUI.

.DESCRIPTION
    1. Runs the test suite (skip with -SkipTests)
    2. Builds with PyInstaller (packaging\ytdlp-gui.spec):
         default   -> ONE self-contained exe:  dist\ytdlp-gui.exe
         -OneDir   -> a folder:                dist\ytdlp-gui\ytdlp-gui.exe (+ _internal\)
    3. Optionally embeds ffmpeg.exe / ffprobe.exe from -FFmpegDir
    4. Smoke-tests the built exe (launches it, waits for the window, closes it)
    5. Copies the result to release\:
         release\ytdlp-gui-<version>-win64.exe   (or a .zip of the folder with -OneDir)

.EXAMPLE
    .\build.ps1
.EXAMPLE
    .\build.ps1 -FFmpegDir C:\tools\ffmpeg\bin
.EXAMPLE
    .\build.ps1 -OneDir
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipSmokeTest,
    [switch]$OneDir,
    [string]$FFmpegDir
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "No virtualenv found. Run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
}

$version = (& $python -c "import sys; sys.path.insert(0, 'src'); from app.constants import APP_VERSION; print(APP_VERSION)").Trim()
$ytdlpVersion = (& $python -c "import yt_dlp.version as v; print(v.__version__)").Trim()
Write-Host "== Building yt-dlp GUI $version (bundling yt-dlp $ytdlpVersion) ==" -ForegroundColor Cyan

if (-not $SkipTests) {
    Write-Host "-- Running tests" -ForegroundColor Cyan
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed; aborting build." }
}

$env:YTDLP_GUI_ONEDIR = if ($OneDir) { '1' } else { '0' }
$env:YTDLP_GUI_FFMPEG_DIR = if ($FFmpegDir) { (Resolve-Path $FFmpegDir).Path } else { '' }
if ($FFmpegDir) { Write-Host "-- Embedding FFmpeg from $FFmpegDir" -ForegroundColor Cyan }

Write-Host "-- Running PyInstaller ($(if ($OneDir) { 'one folder' } else { 'single exe' }))" -ForegroundColor Cyan
& $python -m PyInstaller packaging\ytdlp-gui.spec --noconfirm --clean --log-level WARN
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

if ($OneDir) {
    $exe = Join-Path $PSScriptRoot 'dist\ytdlp-gui\ytdlp-gui.exe'
} else {
    $exe = Join-Path $PSScriptRoot 'dist\ytdlp-gui.exe'
}

if (-not $SkipSmokeTest) {
    Write-Host "-- Smoke-testing $exe" -ForegroundColor Cyan
    $launcher = Start-Process $exe -PassThru
    # A single-file exe unpacks itself first, and the window belongs to a
    # child process, so look for any ytdlp-gui process that owns a window.
    $window = $null
    $deadline = (Get-Date).AddSeconds(60)
    while (-not $window -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $window = Get-Process -Name 'ytdlp-gui' -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowTitle } | Select-Object -First 1
        $launcher.Refresh()
        if ($launcher.HasExited -and -not $window) {
            throw "Smoke test failed: app exited early with code $($launcher.ExitCode). See %APPDATA%\ytdlp-gui\app.log"
        }
    }
    if (-not $window) {
        Get-Process -Name 'ytdlp-gui' -ErrorAction SilentlyContinue | Stop-Process -Force
        throw "Smoke test failed: no main window appeared within 60 seconds."
    }
    $title = $window.MainWindowTitle
    Start-Sleep -Seconds 2
    $null = $window.CloseMainWindow()
    if (-not $launcher.WaitForExit(20000)) {
        Get-Process -Name 'ytdlp-gui' -ErrorAction SilentlyContinue | Stop-Process -Force
        throw "Smoke test failed: app did not close."
    }
    if ($launcher.ExitCode -ne 0) { throw "Smoke test failed: exit code $($launcher.ExitCode)." }
    Write-Host "   OK ('$title' opened and closed cleanly)"
}

$releaseDir = Join-Path $PSScriptRoot 'release'
New-Item -ItemType Directory -Force $releaseDir | Out-Null

# Right after the smoke test, antivirus scanning can briefly keep the exe
# locked, so retry the copy/zip a few times before giving up.
function Invoke-WithRetry([scriptblock]$Action) {
    for ($attempt = 1; ; $attempt++) {
        try { & $Action; return } catch {
            if ($attempt -ge 6) { throw }
            Start-Sleep -Seconds 3
        }
    }
}

if ($OneDir) {
    $output = Join-Path $releaseDir "ytdlp-gui-$version-win64.zip"
    Invoke-WithRetry { Compress-Archive -Path (Split-Path $exe) -DestinationPath $output -Force }
} else {
    $output = Join-Path $releaseDir "ytdlp-gui-$version-win64.exe"
    Invoke-WithRetry { Copy-Item $exe $output -Force }
}

$sizeMB = [math]::Round((Get-Item $output).Length / 1MB, 1)
Write-Host "== Done: $output ($sizeMB MB) ==" -ForegroundColor Green
