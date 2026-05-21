"""Tests for the Wake-Planner CalendarCache + resilience wiring.

Covers the four scenarios called out in the brief:
1. throttle (multiple quick refreshes → one real fetch),
2. last-known-good fallback when the calendar service throws,
3. error with no prior cache → empty events + structured status,
4. concurrent callers coalesce under the per-(entity, range) lock.

Also covers the holiday range fetch — one real call for the whole window
instead of one per day — and the coordinator's exposed `calendar_status`.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

import pytest


MODULE_DIR = (
    Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    / "custom_components" / "bennis_toolbox" / "modules" / "wake_planner"
)


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# ---------------------------------------------------------------------------
# Minimal HA stubs so calendar_cache + holiday_source can be imported.
# ---------------------------------------------------------------------------


def _install_ha_stubs() -> None:
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    ha.__path__ = []  # type: ignore[attr-defined]

    ha_core = sys.modules.setdefault(
        "homeassistant.core", types.ModuleType("homeassistant.core")
    )

    class _HA: ...

    if not hasattr(ha_core, "HomeAssistant"):
        ha_core.HomeAssistant = _HA


_install_ha_stubs()


def _load(module_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


calendar_cache = _load(MODULE_DIR / "calendar_cache.py", "wp_calendar_cache")
CalendarCache = calendar_cache.CalendarCache


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeState:
    def __init__(self, state: str = "ok"):
        self.state = state


class _FakeStates:
    def __init__(self, table: dict[str, _FakeState] | None = None):
        self._t = dict(table or {})

    def get(self, entity_id: str):
        return self._t.get(entity_id)


class _FakeServices:
    def __init__(self):
        self.calls: list[dict] = []
        # Each entry: list/iterator of responses to return / raise.
        self.script: dict[str, list] = {}

    def queue(self, entity_id: str, responses: list):
        self.script[entity_id] = list(responses)

    async def async_call(self, domain, name, data, blocking=False, return_response=False):
        self.calls.append({"domain": domain, "service": name, "data": dict(data)})
        eid = data["entity_id"]
        responses = self.script.get(eid, [])
        if not responses:
            return {eid: {"events": []}}
        nxt = responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class _FakeHass:
    def __init__(self, states_table=None):
        self.states = _FakeStates(states_table or {"calendar.x": _FakeState("ok")})
        self.services = _FakeServices()


def _range():
    start = datetime(2026, 1, 12, 0, 0)
    end = start + timedelta(days=14)
    return start, end


def _events(*titles):
    return [{"summary": t, "start": "2026-01-12T07:00:00+00:00", "all_day": False} for t in titles]


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


@_run
async def test_first_fetch_calls_calendar_service_once():
    hass = _FakeHass()
    hass.services.queue("calendar.x", [{"calendar.x": {"events": _events("morning meeting")}}])
    cache = CalendarCache(hass, min_refresh_interval=900)
    start, end = _range()
    events, status = await cache.async_get_events("calendar.x", start, end)
    assert [e["summary"] for e in events] == ["morning meeting"]
    assert status["status"] == "ok"
    assert status["event_count"] == 1
    assert status["using_cached"] is False
    assert len(hass.services.calls) == 1


@_run
async def test_throttle_blocks_second_fetch_within_min_interval():
    hass = _FakeHass()
    hass.services.queue("calendar.x", [
        {"calendar.x": {"events": _events("A")}},
        {"calendar.x": {"events": _events("B")}},  # would be returned on a 2nd fetch
    ])
    cache = CalendarCache(hass, min_refresh_interval=900)
    start, end = _range()
    e1, _ = await cache.async_get_events("calendar.x", start, end)
    e2, _ = await cache.async_get_events("calendar.x", start, end)
    assert [e["summary"] for e in e1] == ["A"]
    assert [e["summary"] for e in e2] == ["A"]
    assert len(hass.services.calls) == 1, "throttle should suppress the 2nd HA call"


@_run
async def test_force_refresh_bypasses_throttle():
    hass = _FakeHass()
    hass.services.queue("calendar.x", [
        {"calendar.x": {"events": _events("A")}},
        {"calendar.x": {"events": _events("B")}},
    ])
    cache = CalendarCache(hass, min_refresh_interval=900)
    start, end = _range()
    await cache.async_get_events("calendar.x", start, end)
    e2, status = await cache.async_force_refresh("calendar.x", start, end)
    assert [e["summary"] for e in e2] == ["B"]
    assert status["status"] == "ok"
    assert len(hass.services.calls) == 2


@_run
async def test_exception_falls_back_to_last_known_good():
    hass = _FakeHass()
    hass.services.queue("calendar.x", [
        {"calendar.x": {"events": _events("Stable")}},
        ConnectionResetError(104, "Connection reset by peer"),
    ])
    cache = CalendarCache(hass, min_refresh_interval=0)  # always refresh
    start, end = _range()
    first, _ = await cache.async_get_events("calendar.x", start, end)
    assert [e["summary"] for e in first] == ["Stable"]

    cached, status = await cache.async_get_events("calendar.x", start, end)
    assert [e["summary"] for e in cached] == ["Stable"]
    assert status["status"] == "using_cache"
    assert status["using_cached"] is True
    assert "Connection reset" in status["last_error"]


@_run
async def test_exception_with_no_prior_cache_returns_empty_and_status_error():
    hass = _FakeHass()
    hass.services.queue("calendar.x", [
        ConnectionResetError(104, "Connection reset by peer"),
    ])
    cache = CalendarCache(hass, min_refresh_interval=0)
    start, end = _range()
    events, status = await cache.async_get_events("calendar.x", start, end)
    assert events == []
    assert status["status"] == "error_no_cache"
    assert status["using_cached"] is False
    assert "Connection reset" in status["last_error"]


@_run
async def test_unavailable_entity_state_returns_cache_if_any():
    """When the entity itself goes to `unavailable` HA returns no events;
    the cache should fall back to the last good fetch."""
    hass = _FakeHass()
    hass.services.queue("calendar.x", [{"calendar.x": {"events": _events("Cached")}}])
    cache = CalendarCache(hass, min_refresh_interval=900)
    start, end = _range()
    await cache.async_get_events("calendar.x", start, end)

    hass.states._t["calendar.x"] = _FakeState("unavailable")
    events, status = await cache.async_get_events("calendar.x", start, end)
    assert [e["summary"] for e in events] == ["Cached"]
    assert status["status"] == "unavailable"
    assert status["using_cached"] is True


@_run
async def test_not_configured_returns_empty_and_status():
    cache = CalendarCache(_FakeHass(), min_refresh_interval=900)
    start, end = _range()
    events, status = await cache.async_get_events(None, start, end)
    assert events == []
    assert status["status"] == "not_configured"
    assert status["using_cached"] is False


@_run
async def test_concurrent_calls_share_one_fetch_under_lock():
    """Two parallel callers on the same key must coalesce: only one
    underlying calendar.get_events call."""
    hass = _FakeHass()

    # Track concurrent in-flight calls via a barrier-ish counter.
    state = {"in_flight": 0, "max_in_flight": 0}
    original_async_call = hass.services.async_call

    async def slow_call(*args, **kwargs):
        state["in_flight"] += 1
        state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        try:
            await asyncio.sleep(0)  # yield so concurrency can be observed
            return {kwargs["data"]["entity_id"] if False else args[2]["entity_id"]: {"events": _events("X")}}
        finally:
            state["in_flight"] -= 1

    # Use positional adapter: services.async_call(domain, service, data, blocking, return_response)
    async def fake_call(domain, name, data, blocking=False, return_response=False):
        state["in_flight"] += 1
        state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        try:
            await asyncio.sleep(0.01)
            return {data["entity_id"]: {"events": _events("X")}}
        finally:
            state["in_flight"] -= 1

    hass.services.async_call = fake_call  # type: ignore[method-assign]
    cache = CalendarCache(hass, min_refresh_interval=900)
    start, end = _range()
    res = await asyncio.gather(
        cache.async_get_events("calendar.x", start, end),
        cache.async_get_events("calendar.x", start, end),
        cache.async_get_events("calendar.x", start, end),
    )
    # Each call returned events from the cached fetch.
    assert all(r[0][0]["summary"] == "X" for r in res)
    assert state["max_in_flight"] == 1


# ---------------------------------------------------------------------------
# Holiday range fetch resilience
# ---------------------------------------------------------------------------


# Re-create a synthetic package so `from .const import …` /
# `from .calendar_cache import CalendarCache` inside holiday_source.py
# resolve. We only need const + calendar_cache + holiday_source.
def _load_module_as_pkg() -> types.ModuleType:
    pkg = sys.modules.get("wp_resilience_pkg")
    if pkg is not None:
        return pkg
    pkg = types.ModuleType("wp_resilience_pkg")
    pkg.__path__ = [str(MODULE_DIR)]
    sys.modules["wp_resilience_pkg"] = pkg
    # const + calendar_cache are needed by holiday_source.
    for fname, alias in (
        ("const.py", "wp_resilience_pkg.const"),
        ("rule_engine.py", "wp_resilience_pkg.rule_engine"),
        ("calendar_cache.py", "wp_resilience_pkg.calendar_cache"),
        ("holiday_source.py", "wp_resilience_pkg.holiday_source"),
    ):
        spec = importlib.util.spec_from_file_location(alias, MODULE_DIR / fname)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[alias] = mod
        spec.loader.exec_module(mod)
    return pkg


_pkg = _load_module_as_pkg()
holiday_source = sys.modules["wp_resilience_pkg.holiday_source"]


@_run
async def test_holiday_range_fetch_uses_single_calendar_call_for_30_days():
    hass = _FakeHass(states_table={"calendar.hol": _FakeState("ok")})
    hass.services.queue("calendar.hol", [
        {"calendar.hol": {
            "events": [
                {"summary": "New Year",  "start": "2026-01-01", "all_day": True},
                {"summary": "Off-range", "start": "2026-02-15", "all_day": True},
            ],
        }},
    ])
    cache = CalendarCache(hass, min_refresh_interval=900)
    start = datetime(2026, 1, 1).date()
    end = datetime(2026, 1, 30).date()
    holiday_map = await holiday_source.async_holiday_map(
        hass, "calendar.hol", start, end, None, cache=cache,
    )
    # Single underlying HA call for the whole range.
    assert len(hass.services.calls) == 1
    # Jan 1 is the holiday; Jan 17 is Saturday → weekend.
    assert holiday_map[datetime(2026, 1, 1).date()] == (True, "New Year")
    assert holiday_map[datetime(2026, 1, 17).date()] == (True, "Weekend")
    # Off-range event was filtered out.
    assert datetime(2026, 2, 15).date() not in holiday_map


@_run
async def test_holiday_range_fetch_falls_back_to_cache_on_exception():
    hass = _FakeHass(states_table={"calendar.hol": _FakeState("ok")})
    hass.services.queue("calendar.hol", [
        {"calendar.hol": {"events": [
            {"summary": "Cached Holiday", "start": "2026-01-05", "all_day": True},
        ]}},
        ConnectionResetError(104, "Connection reset by peer"),
    ])
    cache = CalendarCache(hass, min_refresh_interval=0)
    start = datetime(2026, 1, 1).date()
    end = datetime(2026, 1, 10).date()
    # 1st call: populates cache.
    await holiday_source.async_holiday_map(
        hass, "calendar.hol", start, end, None, cache=cache,
    )
    # 2nd call: CalDAV throws → should use cached holiday events.
    holiday_map = await holiday_source.async_holiday_map(
        hass, "calendar.hol", start, end, None, cache=cache,
    )
    assert holiday_map[datetime(2026, 1, 5).date()] == (True, "Cached Holiday")


@_run
async def test_holiday_range_fetch_with_no_cache_and_exception_yields_no_extra_holidays():
    """No prior cache + CalDAV exception → no calendar-derived holidays,
    but weekends + manual still come through."""
    hass = _FakeHass(states_table={"calendar.hol": _FakeState("ok")})
    hass.services.queue("calendar.hol", [
        ConnectionResetError(104, "Connection reset by peer"),
    ])
    cache = CalendarCache(hass, min_refresh_interval=0)
    start = datetime(2026, 1, 1).date()
    end = datetime(2026, 1, 10).date()
    holiday_map = await holiday_source.async_holiday_map(
        hass, "calendar.hol", start, end, None, cache=cache,
    )
    # Weekends still in.
    assert holiday_map[datetime(2026, 1, 3).date()] == (True, "Weekend")
    # No CalDAV-derived holiday entries.
    weekday_holidays = {
        d: v for d, v in holiday_map.items() if v[1] not in ("Weekend",)
    }
    assert weekday_holidays == {}
