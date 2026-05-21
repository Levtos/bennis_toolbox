"""Calendar source for Wake Planner (HA calendar entities only).

Fetches go through `CalendarCache` so concurrent callers coalesce, the
HA calendar service is hit at most once per `min_refresh_interval`, and
intermittent CalDAV failures fall back to the last-known-good events
instead of returning empty results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant

from .calendar_cache import CalendarCache
from .const import CalendarDecision, DEFAULT_CALENDAR_WAKE_PATTERN
from .rule_engine import parse_time

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CalendarSourceStatus:
    """Current health of the configured calendar source.

    `ha_calendar` keeps the legacy short string for backward compatibility
    (`not_configured` / `ok` / `unavailable` / `error` / `using_cache`).
    `detail` carries the structured payload from CalendarCache.
    """

    ha_calendar: str = "not_configured"
    detail: dict[str, Any] = field(default_factory=dict)


_CACHE_STATUS_TO_LEGACY = {
    "not_configured": "not_configured",
    "unavailable": "unavailable",
    "never_fetched": "never_fetched",
    "ok": "ok",
    "using_cache": "using_cache",
    "error_no_cache": "error",
}


class CalendarSource:
    """Fetch and parse events from a Home Assistant calendar entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        calendar_entity_id: str | None,
        wake_pattern: str,
        skip_titles: list[str],
        cache: CalendarCache,
    ) -> None:
        self.hass = hass
        self.calendar_entity_id = calendar_entity_id or None
        self.wake_re = re.compile(wake_pattern or DEFAULT_CALENDAR_WAKE_PATTERN, re.IGNORECASE)
        self.skip_titles = [title.strip().lower() for title in skip_titles if title.strip()]
        self.cache = cache
        self.status = CalendarSourceStatus()

    async def async_get_decisions(
        self, person_slugs: list[str], start: datetime, end: datetime
    ) -> dict[tuple[str, date], CalendarDecision]:
        """Return calendar-derived decisions for each person/date."""
        decisions: dict[tuple[str, date], CalendarDecision] = {}
        early_events: dict[date, CalendarDecision] = {}
        for event in await self._async_get_ha_events(start, end):
            summary = str(event.get("summary") or event.get("title") or "")
            event_date = self._event_date(event, start.date())
            decision = self._parse_summary(summary, bool(event.get("all_day")))
            if decision is None:
                event_time = self._event_time(event)
                if event_time is None:
                    continue
                current = early_events.get(event_date)
                if current is None or event_time < current.early_event_time:
                    early_events[event_date] = CalendarDecision(
                        early_event_time=event_time,
                        summary=summary,
                        source="calendar",
                    )
                continue
            for slug in person_slugs:
                decisions[(slug, event_date)] = decision
        for event_date, decision in early_events.items():
            for slug in person_slugs:
                decisions.setdefault((slug, event_date), decision)
        return decisions

    async def _async_get_ha_events(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        events, detail = await self.cache.async_get_events(
            self.calendar_entity_id, start, end
        )
        self.status.detail = detail
        self.status.ha_calendar = _CACHE_STATUS_TO_LEGACY.get(
            detail.get("status", "not_configured"), detail.get("status", "ok"),
        )
        return events

    def _parse_summary(self, summary: str, all_day: bool) -> CalendarDecision | None:
        normalized = summary.strip().lower()
        if all_day and normalized in self.skip_titles:
            return CalendarDecision(skip=True, summary=summary, source="calendar")
        match = self.wake_re.search(summary)
        if not match:
            return None
        value = match.groupdict().get("time") if match.groupdict() else match.group(1)
        try:
            wake = parse_time(value)
        except ValueError:
            return None
        return CalendarDecision(wake_time=wake, summary=summary, source="calendar")

    def _event_date(self, event: dict[str, Any], fallback: date) -> date:
        raw = event.get("start") or event.get("start_time") or event.get("date")
        if isinstance(raw, dict):
            raw = raw.get("dateTime") or raw.get("date")
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    return date.fromisoformat(raw[:10])
                except ValueError:
                    return fallback
        return fallback

    def _event_time(self, event: dict[str, Any]) -> time | None:
        raw = event.get("start") or event.get("start_time")
        if isinstance(raw, dict):
            raw = raw.get("dateTime")
        if not isinstance(raw, str) or len(raw) <= 10:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).time().replace(tzinfo=None)
        except ValueError:
            return None
