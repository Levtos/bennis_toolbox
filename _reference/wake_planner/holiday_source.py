"""Holiday source helpers using weekends and optional HA holiday calendars."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HolidaySource:
    """Read full-day holiday events from a Home Assistant calendar entity."""

    def __init__(self, hass: HomeAssistant, holiday_calendar_entity_id: str | None) -> None:
        self.hass = hass
        self.entity_id = holiday_calendar_entity_id or None

    async def is_holiday(self, check_date: date) -> bool:
        """Return true if check_date has a full-day event in the holiday calendar."""
        if not self.entity_id:
            return False
        start = datetime.combine(check_date, time.min)
        end = datetime.combine(check_date, time.max)
        try:
            response = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": self.entity_id,
                    "start_date_time": start.isoformat(),
                    "end_date_time": end.isoformat(),
                },
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001 - holiday source must not break coordinator
            _LOGGER.debug("Holiday calendar fetch failed for %s: %s", self.entity_id, err)
            return False
        events = (response or {}).get(self.entity_id, {}).get("events", [])
        return any(event.get("all_day") for event in events)


async def async_holiday_map(
    hass: HomeAssistant,
    holiday_calendar_entity_id: str | None,
    start: date,
    end: date,
    manual_holiday_dates: Any = None,
) -> dict[date, tuple[bool, str | None]]:
    """Build a date keyed holiday map from weekends and configured holiday sources."""
    source = HolidaySource(hass, holiday_calendar_entity_id)
    holidays: dict[date, tuple[bool, str | None]] = _manual_holiday_map(
        manual_holiday_dates,
        start,
        end,
    )
    current = start
    while current <= end:
        if current.weekday() >= 5:
            holidays[current] = (True, "Weekend")
        elif await source.is_holiday(current):
            holidays[current] = (True, "Holiday calendar")
        current += timedelta(days=1)
    return holidays


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
