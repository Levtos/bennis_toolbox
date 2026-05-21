"""Internal calendar cache for Wake Planner.

Wake Planner hits two HA calendar entities (regular + holiday) from
multiple places: the 60-second coordinator refresh, the WebSocket
schedule view, and any panel/automation that asks for a schedule. With
CalDAV backends like mailbox.org each such call can fail intermittently
with ``ConnectionResetError(104, 'Connection reset by peer')``. This
cache:

* coalesces concurrent fetches per (entity_id, time range) under an
  asyncio.Lock,
* throttles real HA calendar calls to a minimum interval
  (`min_refresh_interval`, default 15 min),
* keeps the **last-known-good** events on failure so consumers degrade
  gracefully instead of receiving an empty list every time CalDAV is
  cranky,
* surfaces structured status (`ok` / `using_cache` / `error_no_cache` /
  `never_fetched` / `not_configured` / `unavailable`).

It is intentionally HA-light: it only calls
``hass.services.async_call("calendar", "get_events", ...)``. Pure logic
(range-key, status decisions) lives in plain helpers so tests can hit
them without an HA instance.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DEFAULT_MIN_REFRESH_INTERVAL = 900  # 15 min


def make_range_key(start: datetime, end: datetime) -> str:
    """Stable key for a (start, end) datetime pair.

    Truncated to ISO seconds; chunks rounded to the start of the day so
    two calls within the same ``today + 14 days`` window collapse onto a
    single cache entry. Callers are expected to canonicalise their range
    (e.g. start = today 00:00, end = today + N days 00:00) so cache hits
    are common.
    """
    return f"{start.isoformat()}|{end.isoformat()}"


@dataclass
class CacheEntry:
    events: list[dict[str, Any]] | None = None
    last_success_ts: float | None = None      # time.monotonic
    last_success_wall: float | None = None    # time.time
    last_error: str | None = None
    last_error_wall: float | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def derive_status(
    entry: CacheEntry, *, configured: bool, available: bool, just_errored: bool
) -> dict[str, Any]:
    """Compose the status dict that consumers expose alongside events."""
    if not configured:
        status = "not_configured"
    elif not available:
        status = "unavailable"
    elif entry.events is None and entry.last_success_ts is None:
        status = "never_fetched" if entry.last_error is None else "error_no_cache"
    elif just_errored and entry.events is not None:
        status = "using_cache"
    else:
        status = "ok"
    return {
        "status": status,
        "last_success": entry.last_success_wall,
        "last_error": entry.last_error,
        "last_error_at": entry.last_error_wall,
        "using_cached": status == "using_cache",
        "event_count": len(entry.events) if entry.events is not None else 0,
    }


class CalendarCache:
    """Per-coordinator HA-calendar cache."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        min_refresh_interval: int = DEFAULT_MIN_REFRESH_INTERVAL,
    ) -> None:
        self.hass = hass
        self.min_refresh_interval = max(0, int(min_refresh_interval))
        self._entries: dict[tuple[str, str], CacheEntry] = {}
        # Track per-entity-id "config" + "availability" status for the
        # case where we never even attempt a fetch.
        self._meta_status: dict[str, dict[str, Any]] = {}

    # ----- introspection -----

    def status_for(self, entity_id: str) -> dict[str, Any]:
        """Return the latest known status for an entity_id.

        Picks the most recently touched (entity_id, range) tuple so the
        panel sees the freshest result.
        """
        if not entity_id:
            return {
                "status": "not_configured",
                "last_success": None,
                "last_error": None,
                "last_error_at": None,
                "using_cached": False,
                "event_count": 0,
            }
        meta = self._meta_status.get(entity_id)
        if meta is not None:
            return dict(meta)
        return {
            "status": "never_fetched",
            "last_success": None,
            "last_error": None,
            "last_error_at": None,
            "using_cached": False,
            "event_count": 0,
        }

    # ----- main entry point -----

    async def async_get_events(
        self,
        entity_id: str | None,
        start: datetime,
        end: datetime,
        *,
        force: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Return cached or freshly fetched events plus a status dict."""
        if not entity_id:
            status = {
                "status": "not_configured",
                "last_success": None, "last_error": None, "last_error_at": None,
                "using_cached": False, "event_count": 0,
            }
            self._meta_status[entity_id or ""] = status
            return [], status

        state = self.hass.states.get(entity_id)
        if state is None or state.state in {"unavailable", "unknown"}:
            entry = self._entries.get((entity_id, make_range_key(start, end)))
            cached = list(entry.events) if entry and entry.events else []
            status = {
                "status": "unavailable",
                "last_success": entry.last_success_wall if entry else None,
                "last_error": entry.last_error if entry else None,
                "last_error_at": entry.last_error_wall if entry else None,
                "using_cached": bool(cached),
                "event_count": len(cached),
            }
            self._meta_status[entity_id] = status
            return cached, status

        range_key = make_range_key(start, end)
        key = (entity_id, range_key)
        entry = self._entries.get(key)
        if entry is None:
            entry = CacheEntry()
            self._entries[key] = entry

        async with entry.lock:
            now = time.monotonic()
            need_refresh = (
                force
                or entry.last_success_ts is None
                or (now - entry.last_success_ts) >= self.min_refresh_interval
            )
            if not need_refresh and entry.events is not None:
                status = derive_status(
                    entry, configured=True, available=True, just_errored=False,
                )
                # Throttled hit — surface "ok" even if it has been served
                # from memory; the caller cannot tell the difference and
                # does not need to. Mark via `using_cached=False` because
                # the data is still considered current within the
                # min_refresh window.
                self._meta_status[entity_id] = status
                return list(entry.events), status

            try:
                response = await self.hass.services.async_call(
                    "calendar", "get_events",
                    {
                        "entity_id": entity_id,
                        "start_date_time": start.isoformat(),
                        "end_date_time": end.isoformat(),
                    },
                    blocking=True,
                    return_response=True,
                )
            except Exception as err:  # noqa: BLE001 - cache is the resilience layer
                entry.last_error = f"{type(err).__name__}: {err}"
                entry.last_error_wall = time.time()
                _LOGGER.debug(
                    "wake_planner calendar fetch failed for %s: %s", entity_id, err
                )
                cached = list(entry.events) if entry.events is not None else []
                status = derive_status(
                    entry, configured=True, available=True, just_errored=True,
                )
                self._meta_status[entity_id] = status
                return cached, status

            events = list(
                ((response or {}).get(entity_id) or {}).get("events") or []
            )
            entry.events = events
            entry.last_success_ts = now
            entry.last_success_wall = time.time()
            entry.last_error = None
            entry.last_error_wall = None
            status = derive_status(
                entry, configured=True, available=True, just_errored=False,
            )
            self._meta_status[entity_id] = status
            return list(events), status

    async def async_force_refresh(
        self,
        entity_id: str | None,
        start: datetime,
        end: datetime,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return await self.async_get_events(entity_id, start, end, force=True)
