from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from download.history import HistoryEntry, HistoryStore


def _entry(**overrides) -> HistoryEntry:
    defaults = dict(url="https://example.com/v", title="Video", status="completed")
    defaults.update(overrides)
    return HistoryEntry.now(**defaults)


class TestHistoryEntry:
    def test_now_sets_a_timestamp(self):
        entry = _entry()
        assert entry.timestamp

    def test_round_trip_through_dict(self):
        entry = _entry(title="My Video", file_path="/tmp/video.mp4")
        restored = HistoryEntry.from_dict(entry.to_dict())
        assert restored.title == "My Video"
        assert restored.file_path == "/tmp/video.mp4"
        assert restored.id == entry.id

    def test_from_dict_ignores_unknown_keys(self):
        data = {"url": "https://x", "title": "t", "timestamp": "2024-01-01T00:00:00+00:00", "status": "completed", "future_field": "ignored"}
        restored = HistoryEntry.from_dict(data)
        assert restored.url == "https://x"

    def test_ids_are_unique(self):
        assert _entry().id != _entry().id


class TestHistoryStore:
    def test_missing_file_starts_empty(self, tmp_path):
        store = HistoryStore(tmp_path / "history.json")
        assert store.all_entries() == []

    def test_corrupted_file_starts_empty_without_crashing(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text("{not valid json!!!", encoding="utf-8")
        store = HistoryStore(path)
        assert store.all_entries() == []

    def test_add_persists_across_instances(self, tmp_path):
        path = tmp_path / "history.json"
        store = HistoryStore(path)
        store.add(_entry(title="First Video"))

        reloaded = HistoryStore(path)
        assert len(reloaded.all_entries()) == 1
        assert reloaded.all_entries()[0].title == "First Video"

    def test_newest_entry_first(self, tmp_path):
        store = HistoryStore(tmp_path / "history.json")
        store.add(_entry(title="Older"))
        store.add(_entry(title="Newer"))
        titles = [e.title for e in store.all_entries()]
        assert titles == ["Newer", "Older"]

    def test_remove_deletes_the_right_entry(self, tmp_path):
        store = HistoryStore(tmp_path / "history.json")
        store.add(_entry(title="Keep me"))
        to_remove = _entry(title="Remove me")
        store.add(to_remove)

        store.remove(to_remove.id)

        titles = [e.title for e in store.all_entries()]
        assert titles == ["Keep me"]

    def test_clear_empties_and_persists(self, tmp_path):
        path = tmp_path / "history.json"
        store = HistoryStore(path)
        store.add(_entry())
        store.clear()

        assert store.all_entries() == []
        assert HistoryStore(path).all_entries() == []

    def test_get_returns_matching_entry_or_none(self, tmp_path):
        store = HistoryStore(tmp_path / "history.json")
        entry = _entry(title="Findable")
        store.add(entry)

        assert store.get(entry.id).title == "Findable"
        assert store.get("nonexistent-id") is None

    def test_search_matches_title_case_insensitively(self, tmp_path):
        store = HistoryStore(tmp_path / "history.json")
        store.add(_entry(title="Learn Python Basics"))
        store.add(_entry(title="Cooking Pasta"))

        results = store.search("python")
        assert len(results) == 1
        assert results[0].title == "Learn Python Basics"

    def test_search_matches_url(self, tmp_path):
        store = HistoryStore(tmp_path / "history.json")
        store.add(_entry(url="https://example.com/special-video", title="Video"))
        store.add(_entry(url="https://other.com/x", title="Video"))

        results = store.search("special")
        assert len(results) == 1

    def test_search_empty_query_returns_everything(self, tmp_path):
        store = HistoryStore(tmp_path / "history.json")
        store.add(_entry())
        store.add(_entry())
        assert len(store.search("")) == 2
