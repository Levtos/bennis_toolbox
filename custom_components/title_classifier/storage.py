"""Persistent storage for Entity Title Mapper watchers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DEFAULT_ENUM, STORAGE_KEY_PREFIX, STORAGE_VERSION

# A manual hide should not be undone by the very play that prompted it.
# Only resurface manually-hidden entries once they've been quiet this
# long — keeps the currently-playing title hidden after "Ausblenden".
MANUAL_HIDE_GRACE = timedelta(minutes=5)


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO formatted string."""
    return dt_util.utcnow().isoformat()


@dataclass(slots=True)
class MapperEntry:
    """A persisted mapper entry."""

    key: str
    enum: int = DEFAULT_ENUM
    first_seen: str = field(default_factory=utcnow_iso)
    last_seen: str = field(default_factory=utcnow_iso)
    seen_count: int = 0
    hidden_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MapperEntry":
        """Build an entry from stored data."""
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
        """Return a JSON-serialisable representation."""
        return {
            "key": self.key,
            "enum": self.enum,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "seen_count": self.seen_count,
            "hidden_at": self.hidden_at,
        }

    def is_hidden(self, auto_hide_cutoff: datetime | None) -> bool:
        """Return whether the entry is hidden under the given cutoff policy."""
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
    """Storage facade for one watcher."""

    def __init__(self, hass: HomeAssistant, watcher_id: str) -> None:
        """Initialise the store."""
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}{watcher_id}")
        self._entries: dict[str, MapperEntry] = {}

    @property
    def entries(self) -> dict[str, MapperEntry]:
        """Return all known entries keyed by raw key."""
        return self._entries

    async def async_load(self) -> None:
        """Load storage from disk."""
        data = await self._store.async_load()
        raw_entries = (data or {}).get("entries", [])
        self._entries = {
            entry.key: entry
            for entry in (MapperEntry.from_dict(item) for item in raw_entries)
            if entry.key
        }

    async def async_save(self) -> None:
        """Persist storage to disk."""
        await self._store.async_save(
            {"entries": [entry.as_dict() for entry in self.sorted_entries()]}
        )

    def get_enum(self, key: str | None) -> int:
        """Return the enum for a key, falling back to 0."""
        if not key or key not in self._entries:
            return DEFAULT_ENUM
        return self._entries[key].enum

    async def async_seen(self, key: str) -> MapperEntry:
        """Record that a key was seen and persist the update."""
        now = utcnow_iso()
        entry = self._entries.get(key)
        if entry is None:
            entry = MapperEntry(key=key, first_seen=now, last_seen=now, seen_count=0)
            self._entries[key] = entry
        entry.last_seen = now
        entry.seen_count += 1
        if entry.hidden_at is not None:
            # Resurface a manual hide only once the grace window has passed,
            # otherwise the currently-playing title would un-hide itself the
            # moment the user clicked "Ausblenden".
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
        """Set the enum for a key and persist the update."""
        entry = self._set_enum_in_memory(key, enum)
        await self.async_save()
        return entry

    async def async_import_entries(self, entries: list[dict[str, Any]]) -> list[MapperEntry]:
        """Create or update multiple title entries and persist once."""
        imported = [self._set_enum_in_memory(item["key"], item["enum"]) for item in entries]
        await self.async_save()
        return imported

    def merge_keys_in_memory(self, target_key: str, source_keys: list[str]) -> None:
        """Merge source keys into a target key without saving immediately."""
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
        """Create or update an entry without saving immediately."""
        entry = self._entries.get(key)
        if entry is None:
            now = utcnow_iso()
            entry = MapperEntry(key=key, first_seen=now, last_seen=now, seen_count=0)
            self._entries[key] = entry
        entry.enum = enum
        if enum != DEFAULT_ENUM:
            # Classifying always un-hides — a non-default enum means the user
            # wants the entry to participate in matching going forward.
            entry.hidden_at = None
        return entry

    async def async_hide_unmapped(self) -> int:
        """Hide every unmapped entry that is not already hidden."""
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
        """Delete a key and persist when it existed."""
        deleted = self._entries.pop(key, None) is not None
        if deleted:
            await self.async_save()
        return deleted

    async def async_clear_old(self, days: int) -> int:
        """Delete entries not seen for at least the requested number of days."""
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
        """Return entries with unmapped/default entries first, then by last_seen."""
        return sorted(
            self._entries.values(),
            key=lambda item: (item.enum != DEFAULT_ENUM, item.last_seen),
            reverse=False,
        )
