"""Persistent download history: a JSON-backed record of past downloads,
independent of the in-memory queue (which only lives for the current
session — see download/manager.py). Follows the same corrupted/missing
file handling policy as app/config.py: never crash the app over a bad
history file, just start fresh and log a warning.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("ytdlp_gui")


@dataclass
class HistoryEntry:
    url: str
    title: str
    timestamp: str  # ISO 8601, UTC
    status: str  # "completed" | "failed" | "cancelled"
    file_path: str | None = None
    format_description: str | None = None
    size_bytes: int | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        known_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    @classmethod
    def now(cls, **kwargs) -> "HistoryEntry":
        return cls(timestamp=datetime.now(timezone.utc).isoformat(), **kwargs)


class HistoryStore:
    """Loads once at construction, saves on every mutation. Simple and
    correct for the data volumes a download history actually reaches;
    no need for a real database here.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: list[HistoryEntry] = self._load()

    def _load(self) -> list[HistoryEntry]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return [HistoryEntry.from_dict(item) for item in raw]
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning("History file at %s is corrupted (%s); starting fresh.", self._path, exc)
            return []

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps([e.to_dict() for e in self._entries], indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("Failed to save history to %s: %s", self._path, exc)

    def add(self, entry: HistoryEntry) -> None:
        self._entries.insert(0, entry)  # newest first
        self._save()

    def all_entries(self) -> list[HistoryEntry]:
        return list(self._entries)

    def get(self, entry_id: str) -> HistoryEntry | None:
        return next((e for e in self._entries if e.id == entry_id), None)

    def remove(self, entry_id: str) -> None:
        self._entries = [e for e in self._entries if e.id != entry_id]
        self._save()

    def clear(self) -> None:
        self._entries = []
        self._save()

    def search(self, query: str) -> list[HistoryEntry]:
        query = query.strip().lower()
        if not query:
            return self.all_entries()
        return [e for e in self._entries if query in e.title.lower() or query in e.url.lower()]
