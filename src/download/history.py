"""Persistent download history: a JSON-backed record of past downloads,
independent of the in-memory queue (which only lives for the current
session — see download/manager.py).

Loading never raises and never throws away good entries because of bad
ones: each entry is validated individually and invalid ones are skipped.
A file that isn't a JSON list at all (or isn't readable text) is moved
aside to `history.json.corrupt` rather than silently overwritten by the
next save. Same policy as app/config.py.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
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
    def from_dict(cls, data: object) -> "HistoryEntry":
        """Build an entry from untrusted data, or raise ValueError.

        url/title/timestamp/status must be strings (url non-empty).
        Optional fields of the wrong type are dropped rather than failing
        the whole entry, since they're display-only.
        """
        if not isinstance(data, dict):
            raise ValueError(f"history entry must be an object, got {type(data).__name__}")

        for key in ("url", "title", "timestamp", "status"):
            if not isinstance(data.get(key), str):
                raise ValueError(f"history entry field {key!r} must be a string")
        if not data["url"].strip():
            raise ValueError("history entry has an empty url")

        def optional_str(key: str) -> str | None:
            value = data.get(key)
            return value if isinstance(value, str) else None

        size = data.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            size = None

        entry_id = data.get("id")
        kwargs: dict = dict(
            url=data["url"],
            title=data["title"],
            timestamp=data["timestamp"],
            status=data["status"],
            file_path=optional_str("file_path"),
            format_description=optional_str("format_description"),
            size_bytes=size,
        )
        if isinstance(entry_id, str) and entry_id:
            kwargs["id"] = entry_id
        return cls(**kwargs)

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

    def _backup_path(self) -> Path:
        return self._path.with_name(self._path.name + ".corrupt")

    def _load(self) -> list[HistoryEntry]:
        if not self._path.exists():
            return []

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("History file at %s is unreadable (%s); starting fresh.", self._path, exc)
            self._move_aside()
            return []
        except OSError as exc:
            logger.warning("Could not read history file at %s (%s); starting fresh.", self._path, exc)
            return []

        if not isinstance(raw, list):
            logger.warning("History file at %s is not a list; starting fresh.", self._path)
            self._move_aside()
            return []

        entries: list[HistoryEntry] = []
        skipped = 0
        for item in raw:
            try:
                entries.append(HistoryEntry.from_dict(item))
            except ValueError:
                skipped += 1

        if skipped:
            logger.warning("Skipped %d invalid history entr%s in %s.", skipped, "y" if skipped == 1 else "ies", self._path)
            # Skipped entries vanish on the next save, so keep a copy of the
            # original rather than destroying whatever they contained.
            try:
                shutil.copy2(self._path, self._backup_path())
            except OSError as exc:
                logger.warning("Could not back up history file: %s", exc)
        return entries

    def _move_aside(self) -> None:
        try:
            os.replace(self._path, self._backup_path())
        except OSError as exc:
            logger.warning("Could not back up unusable history file %s: %s", self._path, exc)

    def _save(self) -> None:
        """Write atomically (temp file, then replace) so a crash mid-write
        can never leave a truncated history file behind.
        """
        tmp_path = self._path.with_name(self._path.name + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(json.dumps([e.to_dict() for e in self._entries], indent=2), encoding="utf-8")
            os.replace(tmp_path, self._path)
        except OSError as exc:
            logger.error("Failed to save history to %s: %s", self._path, exc)
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

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
