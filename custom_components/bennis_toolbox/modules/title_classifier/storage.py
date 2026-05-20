"""Persistente Speicherung pro Watcher.

Storage-Key: `.storage/bennis_toolbox_title_classifier_entries_<watcher_id>`
(via Toolbox-Helper `make_store`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ...storage import make_store
from .const import DEFAULT_ENUM, MODULE_ID, STORAGE_VERSION

MANUAL_HIDE_GRACE = timedelta(minutes=5)


def utcnow_iso() -> str:
    return dt_util.utcnow().isoformat()


@dataclass(slots=True)
class MapperEntry:
    key: str
    enum: int = DEFAULT_ENUM
    first_seen: str = field(default_factory=utcnow_iso)
    last_seen: str = field(default_factory=utcnow_iso)
    seen_count: int = 0
    hidden_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MapperEntry":
        now = utcnow_iso()
        hidden_at = data.get("hidden_at")
        return cls(
            key=str(data.get("key", "")),
            enum=int(data.get("enum", DEFAULT_ENUM)),
            first_seen=str(data.get("first_seen", now)),
            last_seen=str(data.get("last_seen", now)),
            seen_count=int(data.get("seen_count", 0)),
            hidden_at=hidden_at if isinstance(hidden_at, str) else None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "enum": self.enum,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "seen_count": self.seen_count,
            "hidden_at": self.hidden_at,
        }

    def is_hidden(self, auto_hide_cutoff: datetime | None) -> bool:
        if self.hidden_at is not None:
            return True
        if auto_hide_cutoff is None or self.enum != DEFAULT_ENUM:
            return False
        try:
            last = datetime.fromisoformat(self.last_seen)
        except ValueError:
            return False
        if last.tzinfo is None:
            last = last.replace(tzinfo=dt_util.UTC)
        return last < auto_hide_cutoff


class MapperStore:
    """Storage-Fassade für einen Watcher."""

    def __init__(self, hass: HomeAssistant, watcher_id: str) -> None:
        self._store = make_store(
            hass, MODULE_ID, f"entries_{watcher_id}", version=STORAGE_VERSION
        )
        self._entries: dict[str, MapperEntry] = {}

    @property
    def entries(self) -> dict[str, MapperEntry]:
        return self._entries

    async def async_load(self) -> None:
        data = await self._store.async_load()
        raw_entries = (data or {}).get("entries", [])
        self._entries = {
            entry.key: entry
            for entry in (MapperEntry.from_dict(item) for item in raw_entries)
            if entry.key
        }

    async def async_save(self) -> None:
        await self._store.async_save(
            {"entries": [entry.as_dict() for entry in self.sorted_entries()]}
        )

    def get_enum(self, key: str | None) -> int:
        if not key or key not in self._entries:
            return DEFAULT_ENUM
        return self._entries[key].enum

    async def async_seen(self, key: str) -> MapperEntry:
        now = utcnow_iso()
        entry = self._entries.get(key)
        if entry is None:
            entry = MapperEntry(key=key, first_seen=now, last_seen=now, seen_count=0)
            self._entries[key] = entry
        entry.last_seen = now
        entry.seen_count += 1
        if entry.hidden_at is not None:
            try:
                hidden_at_dt = datetime.fromisoformat(entry.hidden_at)
            except ValueError:
                entry.hidden_at = None
            else:
                if hidden_at_dt.tzinfo is None:
                    hidden_at_dt = hidden_at_dt.replace(tzinfo=dt_util.UTC)
                if dt_util.utcnow() - hidden_at_dt >= MANUAL_HIDE_GRACE:
                    entry.hidden_at = None
        await self.async_save()
        return entry

    async def async_set_enum(self, key: str, enum: int) -> MapperEntry:
        entry = self._set_enum_in_memory(key, enum)
        await self.async_save()
        return entry

    async def async_import_entries(self, entries: list[dict[str, Any]]) -> list[MapperEntry]:
        imported = [self._set_enum_in_memory(item["key"], item["enum"]) for item in entries]
        await self.async_save()
        return imported

    def merge_keys_in_memory(self, target_key: str, source_keys: list[str]) -> None:
        target = self._entries.get(target_key)
        for source_key in source_keys:
            if source_key == target_key:
                continue
            source = self._entries.pop(source_key, None)
            if source is None:
                continue
            if target is None:
                target = MapperEntry(
                    key=target_key,
                    enum=source.enum,
                    first_seen=source.first_seen,
                    last_seen=source.last_seen,
                    seen_count=source.seen_count,
                )
                self._entries[target_key] = target
                continue
            if target.enum == DEFAULT_ENUM and source.enum != DEFAULT_ENUM:
                target.enum = source.enum
            target.first_seen = min(target.first_seen, source.first_seen)
            target.last_seen = max(target.last_seen, source.last_seen)
            target.seen_count += source.seen_count

    def _set_enum_in_memory(self, key: str, enum: int) -> MapperEntry:
        entry = self._entries.get(key)
        if entry is None:
            now = utcnow_iso()
            entry = MapperEntry(key=key, first_seen=now, last_seen=now, seen_count=0)
            self._entries[key] = entry
        entry.enum = enum
        if enum != DEFAULT_ENUM:
            entry.hidden_at = None
        return entry

    async def async_hide_unmapped(self) -> int:
        now = utcnow_iso()
        count = 0
        for entry in self._entries.values():
            if entry.enum == DEFAULT_ENUM and entry.hidden_at is None:
                entry.hidden_at = now
                count += 1
        if count:
            await self.async_save()
        return count

    async def async_delete(self, key: str) -> bool:
        deleted = self._entries.pop(key, None) is not None
        if deleted:
            await self.async_save()
        return deleted

    async def async_clear_old(self, days: int) -> int:
        cutoff = dt_util.utcnow() - timedelta(days=days)
        removed = 0
        for key, entry in list(self._entries.items()):
            try:
                last_seen = datetime.fromisoformat(entry.last_seen)
            except ValueError:
                continue
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=dt_util.UTC)
            if last_seen < cutoff:
                self._entries.pop(key, None)
                removed += 1
        if removed:
            await self.async_save()
        return removed

    def sorted_entries(self) -> list[MapperEntry]:
        return sorted(
            self._entries.values(),
            key=lambda item: (item.enum != DEFAULT_ENUM, item.last_seen),
            reverse=False,
        )
