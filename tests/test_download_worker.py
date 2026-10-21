from __future__ import annotations
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
from backend.ytdlp_backend import YtdlpBackend
from download.worker import DownloadWorker

def _fake_ydl_that_calls_hooks(hook_events: list[dict]):
    def _factory(opts):
        mock_ydl = MagicMock()
        def _download(urls):
            hooks = opts.get("progress_hooks", [])
            for event in hook_events:
                for hook in hooks:
                    hook(event)
        mock_ydl.download.side_effect = _download
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = False
        return mock_ydl
    return _factory

class TestDownloadWorkerSuccess:
    def test_emits_progress_then_succeeded(self, qtbot):
        events = [
            {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100},
            {"status": "finished", "filename": "video.mp4"},
        ]
        backend = YtdlpBackend()
        worker = DownloadWorker(backend, "https://example.com/v", {"format": "best"}, threading.Event())
        received_progress = []
        worker.progress.connect(lambda p: received_progress.append(p))
        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_fake_ydl_that_calls_hooks(events)):
            with qtbot.waitSignal(worker.succeeded, timeout=2000):
                worker.run()
        assert len(received_progress) == 2
        assert received_progress[0].percent == 50.0
        assert received_progress[1].is_finished

class TestDownloadWorkerFailure:
    def test_emits_failed_with_friendly_message(self, qtbot):
        backend = YtdlpBackend()
        worker = DownloadWorker(backend, "https://example.com/v", {"format": "best"}, threading.Event())
        def _factory(opts):
            mock_ydl = MagicMock()
            import yt_dlp
            mock_ydl.download.side_effect = yt_dlp.utils.DownloadError("Video unavailable")
            mock_ydl.__enter__.return_value = mock_ydl
            mock_ydl.__exit__.return_value = False
            return mock_ydl
        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_factory):
            with qtbot.waitSignal(worker.failed, timeout=2000) as blocker:
                worker.run()
        user_message, _technical_detail = blocker.args
        assert "unavailable" in user_message.lower()

class TestDownloadWorkerCancellation:
    def test_setting_cancel_event_mid_download_emits_cancelled_not_failed(self, qtbot):
        cancel_event = threading.Event()
        backend = YtdlpBackend()
        worker = DownloadWorker(backend, "https://example.com/v", {"format": "best"}, cancel_event)
        call_count = {"n": 0}
        def _factory(opts):
            mock_ydl = MagicMock()
            def _download(urls):
                hooks = opts.get("progress_hooks", [])
                for _ in range(10):
                    call_count["n"] += 1
                    if call_count["n"] == 2:
                        cancel_event.set()
                    for hook in hooks:
                        hook({"status": "downloading", "downloaded_bytes": call_count["n"], "total_bytes": 100})
            mock_ydl.download.side_effect = _download
            mock_ydl.__enter__.return_value = mock_ydl
            mock_ydl.__exit__.return_value = False
            return mock_ydl
        failed_received = []
        worker.failed.connect(lambda msg, detail: failed_received.append(msg))
        with patch("backend.ytdlp_backend.yt_dlp.YoutubeDL", side_effect=_factory):
            with qtbot.waitSignal(worker.cancelled, timeout=2000):
                worker.run()
        assert failed_received == []


class TestDownloadWorkerUnexpectedErrors:
    def test_non_backend_exception_becomes_a_generic_failure_not_a_crash(self, qtbot):
        backend = MagicMock()
        backend.download.side_effect = ValueError("boom")
        worker = DownloadWorker(backend, "https://example.com/v", {}, threading.Event())

        with qtbot.waitSignal(worker.failed, timeout=2000) as blocker:
            worker.run()

        user_message, technical_detail = blocker.args
        assert user_message == "An unexpected error occurred."
        assert "boom" in technical_detail
