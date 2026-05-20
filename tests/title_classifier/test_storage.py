"""Tests for the persistent classifier storage layer.

We stub Home Assistant's Store with an in-memory fake to exercise
async_load / async_save / async_set_enum / async_seen / async_delete /
async_clear_old / async_hide_unmapped / sorted_entries / is_hidden, plus
merge_keys_in_memory which underlies media-duplicate resolution.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from functools import wraps
from types import SimpleNamespace

import pytest

import tc_storage as S


def _run(coro_fn):
    """Run an async test function via asyncio.run().

    The project does not have pytest-asyncio installed; this keeps the
    tests dependency-free.
    """
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


class _FakeStore:
    """In-memory replacement for homeassistant.helpers.storage.Store."""

    def __init__(self, _hass, _version, _key):
        self._data = None

    async def async_load(self):
        return self._data

    async def async_save(self, data):
        self._data = data


@pytest.fixture
def make_store_factory(monkeypatch):
    """Patch `make_store` inside the loaded tc_storage module."""
    monkeypatch.setattr(S, "make_store", lambda hass, mid, suffix, version=1: _FakeStore(hass, version, suffix))


@_run
async def test_async_seen_creates_then_updates(make_store_factory):
    store = S.MapperStore(hass=SimpleNamespace(), watcher_id="w1")
    entry = await store.async_seen("Stardew Valley")
    assert entry.key == "Stardew Valley"
    assert entry.seen_count == 1
    again = await store.async_seen("Stardew Valley")
    assert again.seen_count == 2
    assert again is entry


@_run
async def test_set_enum_then_get_enum(make_store_factory):
    store = S.MapperStore(SimpleNamespace(), "w1")
    await store.async_seen("Hades")
    await store.async_set_enum("Hades", 3)
    assert store.get_enum("Hades") == 3
    assert store.get_enum(None) == 0
    assert store.get_enum("never seen") == 0


@_run
async def test_set_enum_unhides_entry(make_store_factory):
    store = S.MapperStore(SimpleNamespace(), "w1")
    await store.async_seen("Spelunky")
    await store.async_hide_unmapped()
    assert store.entries["Spelunky"].hidden_at is not None
    await store.async_set_enum("Spelunky", 2)
    assert store.entries["Spelunky"].hidden_at is None


@_run
async def test_delete_returns_truthiness(make_store_factory):
    store = S.MapperStore(SimpleNamespace(), "w1")
    await store.async_seen("Tetris")
    assert await store.async_delete("Tetris") is True
    assert await store.async_delete("Tetris") is False


@_run
async def test_import_entries_bulk(make_store_factory):
    store = S.MapperStore(SimpleNamespace(), "w1")
    await store.async_import_entries([
        {"key": "Game A", "enum": 1},
        {"key": "Game B", "enum": 2},
    ])
    assert store.get_enum("Game A") == 1
    assert store.get_enum("Game B") == 2


@_run
async def test_clear_old_removes_stale_entries(monkeypatch, make_store_factory):
    store = S.MapperStore(SimpleNamespace(), "w1")
    await store.async_seen("Fresh")
    # Backdate one entry deep into history.
    old_iso = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    store.entries["Fresh"].last_seen = old_iso
    await store.async_seen("Today")
    removed = await store.async_clear_old(days=30)
    assert removed == 1
    assert "Fresh" not in store.entries
    assert "Today" in store.entries


@_run
async def test_hide_unmapped_only_hides_default_enum(make_store_factory):
    store = S.MapperStore(SimpleNamespace(), "w1")
    await store.async_seen("Mapped")
    await store.async_set_enum("Mapped", 4)
    await store.async_seen("Unmapped")
    hidden = await store.async_hide_unmapped()
    assert hidden == 1
    assert store.entries["Mapped"].hidden_at is None
    assert store.entries["Unmapped"].hidden_at is not None
    # Second call does nothing further.
    assert await store.async_hide_unmapped() == 0


@_run
async def test_persistence_round_trip(make_store_factory):
    store = S.MapperStore(SimpleNamespace(), "w1")
    await store.async_seen("Persist Me")
    await store.async_set_enum("Persist Me", 5)
    # Build a second store sharing the same backing payload by injecting it.
    raw = {"entries": [e.as_dict() for e in store.sorted_entries()]}
    store2 = S.MapperStore(SimpleNamespace(), "w1")
    store2._store._data = raw
    await store2.async_load()
    assert store2.get_enum("Persist Me") == 5


def test_is_hidden_obeys_manual_flag():
    entry = S.MapperEntry(key="K", enum=0)
    assert not entry.is_hidden(auto_hide_cutoff=None)
    entry.hidden_at = datetime.now(timezone.utc).isoformat()
    assert entry.is_hidden(auto_hide_cutoff=None)


def test_is_hidden_obeys_auto_cutoff():
    entry = S.MapperEntry(key="K", enum=0)
    entry.last_seen = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=5)
    assert entry.is_hidden(auto_hide_cutoff=cutoff)


def test_is_hidden_mapped_entry_is_never_auto_hidden():
    entry = S.MapperEntry(key="K", enum=4)
    entry.last_seen = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    assert not entry.is_hidden(auto_hide_cutoff=cutoff)


def test_sorted_entries_unmapped_first():
    s = S.MapperStore(SimpleNamespace(), "w1")
    s._entries = {
        "A": S.MapperEntry(key="A", enum=1, last_seen="2026-01-10T00:00:00+00:00"),
        "B": S.MapperEntry(key="B", enum=0, last_seen="2026-01-05T00:00:00+00:00"),
        "C": S.MapperEntry(key="C", enum=0, last_seen="2026-01-12T00:00:00+00:00"),
    }
    keys = [e.key for e in s.sorted_entries()]
    # Default-enum entries first, ordered by last_seen ASC; then the mapped one.
    assert keys == ["B", "C", "A"]


def test_merge_keys_in_memory_combines_seen_counts():
    s = S.MapperStore(SimpleNamespace(), "w1")
    s._entries = {
        "Daft Punk - Get Lucky": S.MapperEntry(
            key="Daft Punk - Get Lucky", enum=0,
            first_seen="2026-01-01T00:00:00+00:00",
            last_seen="2026-01-10T00:00:00+00:00",
            seen_count=3,
        ),
        "Daft Punk feat. Pharrell - Get Lucky (Radio Edit)": S.MapperEntry(
            key="Daft Punk feat. Pharrell - Get Lucky (Radio Edit)", enum=2,
            first_seen="2026-01-05T00:00:00+00:00",
            last_seen="2026-01-15T00:00:00+00:00",
            seen_count=7,
        ),
    }
    s.merge_keys_in_memory(
        target_key="Daft Punk feat. Pharrell - Get Lucky (Radio Edit)",
        source_keys=["Daft Punk - Get Lucky"],
    )
    target = s.entries["Daft Punk feat. Pharrell - Get Lucky (Radio Edit)"]
    assert target.seen_count == 10
    assert target.first_seen == "2026-01-01T00:00:00+00:00"
    assert target.last_seen == "2026-01-15T00:00:00+00:00"
    assert "Daft Punk - Get Lucky" not in s.entries
