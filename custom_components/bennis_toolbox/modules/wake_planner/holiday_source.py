"""Holiday source helpers using weekends and optional HA holiday calendars.

Holiday events are now fetched as a **single range query** through
`CalendarCache` instead of one-call-per-day. Failures fall back to the
last-known-good event list, so a flaky CalDAV holiday calendar can no
longer break the entire wake-planner update loop.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant

from .calendar_cache import CalendarCache

_LOGGER = logging.getLogger(__name__)


class HolidaySource:
    """Read full-day holiday events from a Home Assistant calendar entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        holiday_calendar_entity_id: str | None,
        *,
        cache: CalendarCache,
    ) -> None:
        self.hass = hass
        self.entity_id = holiday_calendar_entity_id or None
        self.cache = cache
        self.last_status: dict[str, Any] = {}

    async def async_fetch_range(
        self, start: date, end: date
    ) -> tuple[dict[date, str], dict[str, Any]]:
        """Fetch the holiday calendar once for the whole range.

        Returns a mapping ``date -> first matching all-day summary`` and the
        cache status dict.
        """
        if not self.entity_id:
            return {}, {
                "status": "not_configured",
                "last_success": None, "last_error": None, "last_error_at": None,
                "using_cached": False, "event_count": 0,
            }
        # Day boundaries so the same range key is hit on coordinator ticks
        # and on-demand WS requests.
        start_dt = datetime.combine(start, time.min)
        end_dt = datetime.combine(end + timedelta(days=1), time.min)
        events, status = await self.cache.async_get_events(
            self.entity_id, start_dt, end_dt
        )
        self.last_status = status
        out: dict[date, str] = {}
        for event in events:
            if not _is_all_day_event(event):
                continue
            event_date = _event_date(event)
            if event_date is None:
                continue
            if start <= event_date <= end:
                out.setdefault(
                    event_date,
                    str(event.get("summary") or event.get("title") or "Holiday calendar"),
                )
        return out, status


async def async_holiday_map(
    hass: HomeAssistant,
    holiday_calendar_entity_id: str | None,
    start: date,
    end: date,
    manual_holiday_dates: Any = None,
    *,
    cache: CalendarCache,
) -> dict[date, tuple[bool, str | None]]:
    """Build a date-keyed holiday map from weekends and configured sources.

    The holiday calendar (if any) is read **once** for the whole range
    instead of per day; failures fall back to the cached event list.
    """
    source = HolidaySource(hass, holiday_calendar_entity_id, cache=cache)
    holiday_events, _status = await source.async_fetch_range(start, end)

    holidays: dict[date, tuple[bool, str | None]] = _manual_holiday_map(
        manual_holiday_dates, start, end,
    )
    current = start
    while current <= end:
        if current.weekday() >= 5:
            holidays[current] = (True, "Weekend")
        elif current in holiday_events:
            holidays[current] = (True, holiday_events[current])
        current += timedelta(days=1)
    return holidays


def _event_date(event: dict[str, Any]) -> date | None:
    raw = event.get("start") or event.get("start_time") or event.get("date")
    if isinstance(raw, dict):
        raw = raw.get("date") or raw.get("dateTime")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
    return None


def _is_all_day_event(event: dict[str, Any]) -> bool:
    """Return true for HA calendar full-day event shapes."""
    if event.get("all_day") is True:
        return True
    raw = event.get("start") or event.get("start_time") or event.get("date")
    if isinstance(raw, dict):
        return bool(raw.get("date") and not raw.get("dateTime"))
    if isinstance(raw, str):
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw[:10])) and len(raw) <= 10
    return False


def _manual_holiday_map(
    configured_dates: Any,
    start: date,
    end: date,
) -> dict[date, tuple[bool, str | None]]:
    """Parse manually configured dates and ranges into holiday map entries."""
    holidays: dict[date, tuple[bool, str | None]] = {}
    if not configured_dates:
        return holidays

    raw_dates = configured_dates
    if isinstance(configured_dates, str):
        raw_dates = re.split(r"[,;\n]+", configured_dates)

    for raw_item in raw_dates:
        if not raw_item:
            continue
        item = str(raw_item).strip()
        if not item:
            continue
        range_match = re.fullmatch(
            r"(.+?)\s*(?:\.\.|/|to|bis)\s*(.+)",
            item,
            flags=re.IGNORECASE,
        )
        if range_match:
            _add_manual_range(holidays, range_match.group(1), range_match.group(2), start, end)
            continue
        _add_manual_range(holidays, item, item, start, end)
    return holidays


def _parse_manual_date(raw_value: str, year: int) -> date | None:
    """Parse one manual date in yearly or one-off syntax."""
    value = raw_value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        if re.fullmatch(r"\d{8}", value):
            return date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:]}")
        if re.fullmatch(r"\d{2}-\d{2}", value):
            return date.fromisoformat(f"{year}-{value}")
        if re.fullmatch(r"\d{4}", value):
            return date.fromisoformat(f"{year}-{value[:2]}-{value[2:]}")
    except ValueError:
        return None
    return None


def _add_manual_range(
    holidays: dict[date, tuple[bool, str | None]],
    raw_start: str,
    raw_end: str,
    map_start: date,
    map_end: date,
) -> None:
    """Add a parsed manual holiday range to the map."""
    added = False
    for year in range(map_start.year, map_end.year + 1):
        range_start = _parse_manual_date(raw_start, year)
        range_end = _parse_manual_date(raw_end, year)
        if range_start is None or range_end is None:
            continue

        if range_end < range_start:
            range_start, range_end = range_end, range_start

        current = max(range_start, map_start)
        last = min(range_end, map_end)
        while current <= last:
            holidays[current] = (True, "Manual holiday")
            current += timedelta(days=1)
            added = True
        if len(raw_start.strip()) >= 8 and len(raw_end.strip()) >= 8:
            return

    if not added:
        _LOGGER.debug("Ignoring invalid manual holiday date/range: %s..%s", raw_start, raw_end)
