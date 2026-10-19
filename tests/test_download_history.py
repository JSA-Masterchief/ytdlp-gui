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


# --- robustness against malformed history files ------------------------------

import json  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402

_GOOD = {"url": "https://a", "title": "Good", "timestamp": "2024-01-01T00:00:00+00:00", "status": "completed"}


class TestEntryValidation:
    def test_valid_dict_builds_an_entry(self):
        entry = HistoryEntry.from_dict(_GOOD)
        assert entry.title == "Good"

    @pytest.mark.parametrize("not_a_dict", [None, "text", 5, [1], True])
    def test_non_dict_raises_value_error(self, not_a_dict):
        with pytest.raises(ValueError):
            HistoryEntry.from_dict(not_a_dict)

    @pytest.mark.parametrize("missing", ["url", "title", "timestamp", "status"])
    def test_missing_required_field_raises(self, missing):
        data = {k: v for k, v in _GOOD.items() if k != missing}
        with pytest.raises(ValueError):
            HistoryEntry.from_dict(data)

    @pytest.mark.parametrize("field", ["url", "title", "timestamp", "status"])
    @pytest.mark.parametrize("bad_value", [None, 5, [], {}, True])
    def test_wrong_typed_required_field_raises(self, field, bad_value):
        with pytest.raises(ValueError):
            HistoryEntry.from_dict({**_GOOD, field: bad_value})

    def test_blank_url_raises(self):
        with pytest.raises(ValueError):
            HistoryEntry.from_dict({**_GOOD, "url": "   "})

    def test_empty_title_is_allowed(self):
        assert HistoryEntry.from_dict({**_GOOD, "title": ""}).title == ""

    def test_wrong_typed_optional_fields_are_dropped_not_fatal(self):
        entry = HistoryEntry.from_dict({**_GOOD, "file_path": 5, "format_description": [], "size_bytes": "big"})
        assert entry.file_path is None
        assert entry.format_description is None
        assert entry.size_bytes is None

    @pytest.mark.parametrize("bad_size", [-1, True, 1.5])
    def test_invalid_size_is_dropped(self, bad_size):
        assert HistoryEntry.from_dict({**_GOOD, "size_bytes": bad_size}).size_bytes is None

    def test_valid_optional_fields_are_kept(self):
        entry = HistoryEntry.from_dict({**_GOOD, "file_path": "/x.mp4", "format_description": "1080p", "size_bytes": 10})
        assert (entry.file_path, entry.format_description, entry.size_bytes) == ("/x.mp4", "1080p", 10)

    def test_missing_or_invalid_id_gets_a_fresh_one(self):
        assert HistoryEntry.from_dict(_GOOD).id
        assert HistoryEntry.from_dict({**_GOOD, "id": 5}).id
        assert HistoryEntry.from_dict({**_GOOD, "id": ""}).id

    def test_existing_id_is_preserved(self):
        assert HistoryEntry.from_dict({**_GOOD, "id": "abc"}).id == "abc"


class TestStoreLoadingMalformedFiles:
    def _write(self, tmp_path, text):
        path = tmp_path / "history.json"
        path.write_text(text, encoding="utf-8")
        return path

    @pytest.mark.parametrize(
        "text",
        ['{"entries": []}', "null", '"hello"', "42", "true"],
    )
    def test_non_list_root_does_not_crash_and_is_backed_up(self, tmp_path, text):
        path = self._write(tmp_path, text)
        store = HistoryStore(path)
        assert store.all_entries() == []
        assert not path.exists()
        assert (tmp_path / "history.json.corrupt").read_text(encoding="utf-8") == text

    def test_non_utf8_bytes_do_not_crash_and_are_backed_up(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_bytes(b"\xff\xfe\x00bad")
        assert HistoryStore(path).all_entries() == []
        assert (tmp_path / "history.json.corrupt").exists()

    def test_invalid_json_is_backed_up_not_destroyed(self, tmp_path):
        path = self._write(tmp_path, "[{broken")
        HistoryStore(path)
        assert (tmp_path / "history.json.corrupt").read_text(encoding="utf-8") == "[{broken"

    @pytest.mark.parametrize("junk", ["5", '"str"', "null", "[]", '{"title": "no url"}'])
    def test_invalid_entries_are_skipped_but_good_ones_survive(self, tmp_path, junk):
        path = self._write(tmp_path, f"[{json.dumps(_GOOD)}, {junk}]")
        store = HistoryStore(path)
        assert [e.title for e in store.all_entries()] == ["Good"]

    def test_skipping_entries_keeps_a_backup_of_the_original(self, tmp_path):
        original = f'[{json.dumps(_GOOD)}, 5]'
        path = self._write(tmp_path, original)
        HistoryStore(path)
        assert (tmp_path / "history.json.corrupt").read_text(encoding="utf-8") == original
        assert path.exists()  # still the live file

    def test_fully_valid_file_creates_no_backup(self, tmp_path):
        path = self._write(tmp_path, f"[{json.dumps(_GOOD)}]")
        HistoryStore(path)
        assert not (tmp_path / "history.json.corrupt").exists()

    def test_wrong_typed_fields_no_longer_reach_the_ui(self, tmp_path):
        """Regression: an entry with title=null / status=[] used to load fine
        and then crash the History page when it rendered the row.
        """
        bad = {"url": "https://a", "title": None, "timestamp": 1, "status": []}
        store = HistoryStore(self._write(tmp_path, json.dumps([bad, _GOOD])))
        assert [e.title for e in store.all_entries()] == ["Good"]

    def test_backup_failure_does_not_crash_loading(self, tmp_path):
        path = self._write(tmp_path, "[1")
        with patch("download.history.os.replace", side_effect=OSError("nope")):
            assert HistoryStore(path).all_entries() == []

    def test_empty_list_loads_as_empty(self, tmp_path):
        assert HistoryStore(self._write(tmp_path, "[]")).all_entries() == []


class TestStoreSaving:
    def test_save_leaves_no_temp_file_behind(self, tmp_path):
        store = HistoryStore(tmp_path / "history.json")
        store.add(_entry())
        assert sorted(p.name for p in tmp_path.iterdir()) == ["history.json"]

    def test_failed_write_does_not_crash_or_clobber_existing_history(self, tmp_path):
        path = tmp_path / "history.json"
        store = HistoryStore(path)
        store.add(_entry(title="Kept"))

        with patch("download.history.os.replace", side_effect=OSError("boom")):
            store.add(_entry(title="Lost"))  # must not raise

        assert [e.title for e in HistoryStore(path).all_entries()] == ["Kept"]
        assert sorted(p.name for p in tmp_path.iterdir()) == ["history.json"]

    def test_round_trip_preserves_all_fields(self, tmp_path):
        path = tmp_path / "history.json"
        store = HistoryStore(path)
        original = _entry(title="Full", file_path="/x.mp4", format_description="720p", size_bytes=123)
        store.add(original)
        loaded = HistoryStore(path).all_entries()[0]
        assert loaded == original
