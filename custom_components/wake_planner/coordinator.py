"""DataUpdateCoordinator for Wake Planner."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import uuid
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .calendar_source import CalendarSource
from .const import (
    CONF_CALENDAR_ENTITY_ID,
    CONF_CALENDAR_SKIP_TITLES,
    CONF_CALENDAR_WAKE_PATTERN,
    CONF_HOLIDAY_BEHAVIOR,
    CONF_HOLIDAY_CALENDAR_ENTITY_ID,
    CONF_MANUAL_HOLIDAY_DATES,
    CONF_PERSON_ENTITY_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    CONF_RULES,
    CONF_SLUG,
    CONF_WAKE_WINDOW_MINUTES,
    DEFAULT_CALENDAR_SKIP_TITLES,
    DEFAULT_CALENDAR_WAKE_PATTERN,
    DEFAULT_WAKE_WINDOW_MINUTES,
    DOMAIN,
    EVENT_WAKE_TRIGGERED,
    HOLIDAY_SKIP,
    STORAGE_KEY,
    STORAGE_VERSION,
    PersonConfig,
    RuntimePersonState,
    WakeDecision,
)
from .holiday_source import async_holiday_map
from .rule_engine import RuleEngine, parse_date, parse_time
from .util import default_rules, persons_from_entry, rule_to_dict

_LOGGER = logging.getLogger(__name__)


class WakePlannerCoordinator(DataUpdateCoordinator[dict[str, WakeDecision]]):
    """Coordinate wake decisions and persisted runtime state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=60),
        )
        self.entry = entry
        self.store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        self.runtime_states: dict[str, RuntimePersonState] = {}
        self.persons: list[PersonConfig] = persons_from_entry(entry)
        self.calendar_source = self._build_calendar_source()
        self.last_update_iso: str | None = None
        self.next_wakes: dict[str, datetime | None] = {}
        self._fired_wake_keys: set[str] = set()

    # --- persistence ----------------------------------------------------

    async def async_load(self) -> None:
        stored = await self.store.async_load() or {}
        for slug, raw in (stored.get("runtime_states") or {}).items():
            self.runtime_states[slug] = RuntimePersonState(
                skip_next=bool(raw.get("skip_next")),
                override_time=parse_time(raw["override_time"]) if raw.get("override_time") else None,
                override_until=parse_date(raw.get("override_until")),
            )
        for person in self.persons:
            self.runtime_states.setdefault(person.slug, RuntimePersonState())

    async def async_save(self) -> None:
        payload: dict[str, Any] = {"runtime_states": {}}
        for slug, state in self.runtime_states.items():
            payload["runtime_states"][slug] = {
                "skip_next": state.skip_next,
                "override_time": state.override_time.strftime("%H:%M") if state.override_time else None,
                "override_until": state.override_until.isoformat() if state.override_until else None,
            }
        await self.store.async_save(payload)

    # --- core update loop ----------------------------------------------

    async def _async_update_data(self) -> dict[str, WakeDecision]:
        current_options = {**self.entry.data, **self.entry.options}
        if current_options != getattr(self, "_last_options", None):
            self.persons = persons_from_entry(self.entry)
            self.calendar_source = self._build_calendar_source()
            self._last_options = current_options
        for person in self.persons:
            self.runtime_states.setdefault(person.slug, RuntimePersonState())
        now = dt_util.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        calendar_decisions = await self.calendar_source.async_get_decisions(
            [person.slug for person in self.persons], start, start + timedelta(days=30)
        )
        holiday_map = await async_holiday_map(
            self.hass,
            self.options.get(CONF_HOLIDAY_CALENDAR_ENTITY_ID),
            start.date(),
            (start + timedelta(days=30)).date(),
            self.options.get(CONF_MANUAL_HOLIDAY_DATES),
        )
        engine = RuleEngine(
            runtime_states=self.runtime_states,
            calendar_decisions=calendar_decisions,
            holiday_by_date=holiday_map,
            holiday_behavior=self.options.get(CONF_HOLIDAY_BEHAVIOR, HOLIDAY_SKIP),
        )
        data = {person.slug: engine.decide(person, now) for person in self.persons}
        self.next_wakes = {person.slug: engine.next_wake(person, now) for person in self.persons}
        for slug, next_wake in self.next_wakes.items():
            if slug in data:
                data[slug].next_wake = next_wake
        self.last_update_iso = now.isoformat()

        self._fire_wake_events(data, now)
        return data

    def _fire_wake_events(self, data: dict[str, WakeDecision], now: datetime) -> None:
        """Fire wake_planner_wake_triggered when a window opens for a person."""
        for person in self.persons:
            decision = data.get(person.slug)
            if not decision or decision.wake_window_start is None or decision.wake_window_end is None:
                continue
            if not (decision.wake_window_start <= now <= decision.wake_window_end):
                continue
            key = f"{person.slug}:{decision.wake_window_start.isoformat()}"
            if key in self._fired_wake_keys:
                continue
            self._fired_wake_keys.add(key)
            self.hass.bus.async_fire(
                EVENT_WAKE_TRIGGERED,
                {
                    "person_id": person.slug,
                    "name": person.name,
                    "wake_time": decision.wake_time.strftime("%H:%M") if decision.wake_time else None,
                    "decided_by": decision.decided_by,
                    "matched_rule_id": decision.matched_rule_id,
                },
            )
        # cap memory
        if len(self._fired_wake_keys) > 200:
            self._fired_wake_keys = set(list(self._fired_wake_keys)[-100:])

    @property
    def options(self) -> dict[str, Any]:
        """Merged entry data and options."""
        return {**self.entry.data, **self.entry.options}

    # --- runtime mutations ---------------------------------------------

    async def async_skip_next(self, person_id: str) -> None:
        state = self._runtime_for(person_id)
        state.skip_next = True
        await self.async_save()
        await self.async_request_refresh()

    async def async_set_override(self, person_id: str, wake_time: str, until: str | date | None) -> None:
        state = self._runtime_for(person_id)
        state.override_time = parse_time(wake_time)
        state.override_until = until if isinstance(until, date) else parse_date(until)
        await self.async_save()
        await self.async_request_refresh()

    async def async_clear_override(self, person_id: str) -> None:
        state = self._runtime_for(person_id)
        state.override_time = None
        state.override_until = None
        state.skip_next = False
        await self.async_save()
        await self.async_request_refresh()

    # --- person / rule editing (used by services + WS API) --------------

    # --- person / rule editing (used by services + WS API) --------------

    def _options_persons(self) -> list[dict[str, Any]]:
        all_opts = {**self.entry.data, **self.entry.options}
        return [dict(p) for p in (all_opts.get(CONF_PERSONS) or [])]

    async def _save_persons(self, persons: list[dict[str, Any]]) -> None:
        new_options = {**self.entry.options, CONF_PERSONS: persons}
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)
        self.persons = persons_from_entry(self.entry)
        await self.async_request_refresh()

    async def async_add_person(self, name: str, person_entity_id: str | None = None) -> str:
        """Create a new person with a default rule set; return its slug."""
        slug_base = slugify(name) or f"person_{uuid.uuid4().hex[:6]}"
        persons = self._options_persons()
        existing = {p.get(CONF_SLUG) for p in persons}
        slug = slug_base
        counter = 2
        while slug in existing:
            slug = f"{slug_base}_{counter}"
            counter += 1
        persons.append({
            CONF_SLUG: slug,
            CONF_PERSON_NAME: name,
            CONF_PERSON_ENTITY_ID: person_entity_id or None,
            CONF_WAKE_WINDOW_MINUTES: DEFAULT_WAKE_WINDOW_MINUTES,
            CONF_RULES: default_rules(),
        })
        await self._save_persons(persons)
        return slug

    async def async_remove_person(self, person_id: str) -> None:
        persons = [p for p in self._options_persons() if p.get(CONF_SLUG) != person_id]
        await self._save_persons(persons)

    async def async_update_person(self, person_id: str, **updates: Any) -> None:
        persons = self._options_persons()
        for i, p in enumerate(persons):
            if p.get(CONF_SLUG) == person_id:
                persons[i] = {**p, **updates}
                break
        else:
            raise ValueError(f"Unknown person {person_id}")
        await self._save_persons(persons)

    async def async_set_rules(self, person_id: str, rules: list[dict[str, Any]]) -> None:
        await self.async_update_person(person_id, **{CONF_RULES: rules})

    async def async_update_global_config(self, **updates: Any) -> None:
        new_options = {**self.entry.options, **updates}
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)
        await self.async_request_refresh()

    # --- helpers --------------------------------------------------------

    def _runtime_for(self, person_id: str) -> RuntimePersonState:
        if person_id not in {person.slug for person in self.persons}:
            raise ValueError(f"Unknown Wake Planner person_id: {person_id}")
        return self.runtime_states.setdefault(person_id, RuntimePersonState())

    def _build_calendar_source(self) -> CalendarSource:
        options = self.options
        skip_titles = str(options.get(CONF_CALENDAR_SKIP_TITLES, DEFAULT_CALENDAR_SKIP_TITLES)).split(",")
        return CalendarSource(
            self.hass,
            calendar_entity_id=options.get(CONF_CALENDAR_ENTITY_ID),
            wake_pattern=options.get(CONF_CALENDAR_WAKE_PATTERN, DEFAULT_CALENDAR_WAKE_PATTERN),
            skip_titles=skip_titles,
        )

    async def async_get_schedule(self, days: int = 14) -> list[dict[str, Any]]:
        """Return per-day, per-person decisions for the next `days` days.

        Used by the panel's 14-day overview so holidays, date-range rules and
        calendar overrides apply to future days too — not just today.
        """
        now = dt_util.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=days)
        calendar_decisions = await self.calendar_source.async_get_decisions(
            [p.slug for p in self.persons], start, end
        )
        holiday_map = await async_holiday_map(
            self.hass,
            self.options.get(CONF_HOLIDAY_CALENDAR_ENTITY_ID),
            start.date(),
            end.date(),
            self.options.get(CONF_MANUAL_HOLIDAY_DATES),
        )
        engine = RuleEngine(
            runtime_states=self.runtime_states,
            calendar_decisions=calendar_decisions,
            holiday_by_date=holiday_map,
            holiday_behavior=self.options.get(CONF_HOLIDAY_BEHAVIOR, HOLIDAY_SKIP),
        )
        out: list[dict[str, Any]] = []
        for offset in range(days):
            day = (start + timedelta(days=offset)).date()
            day_entry: dict[str, Any] = {
                "date": day.isoformat(),
                "holiday_name": holiday_map.get(day, (False, None))[1],
                "is_holiday": holiday_map.get(day, (False, None))[0],
                "persons": {},
            }
            for person in self.persons:
                decision = engine._decide_for_date(person, day, now)  # noqa: SLF001
                day_entry["persons"][person.slug] = decision.as_dict()
            out.append(day_entry)
        return out

    def serialize_person(self, person: PersonConfig) -> dict[str, Any]:
        """Return a JSON-friendly dict for a person + their current state."""
        decision = self.data.get(person.slug) if self.data else None
        runtime = self.runtime_states.get(person.slug)
        return {
            "slug": person.slug,
            "name": person.name,
            "person_entity_id": person.person_entity_id,
            "wake_window_minutes": person.wake_window_minutes,
            "rules": [rule_to_dict(r) for r in person.rules],
            "decision": decision.as_dict() if decision else None,
            "next_wake": self.next_wakes.get(person.slug).isoformat() if self.next_wakes.get(person.slug) else None,
            "skip_next": bool(runtime and runtime.skip_next),
            "override_time": runtime.override_time.strftime("%H:%M") if runtime and runtime.override_time else None,
            "override_until": runtime.override_until.isoformat() if runtime and runtime.override_until else None,
        }
