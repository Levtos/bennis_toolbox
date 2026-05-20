"""Constants and data models for the Wake Planner module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any

# Modulinterne Kennung. Die externe HA-Domäne ist `bennis_toolbox`; das
# Modul-Präfix wird über Helper aus `bennis_toolbox.const` gebaut (storage_key,
# service_name, websocket_type, …).
MODULE_ID = "wake_planner"
NAME = "Wake Planner"

CONF_PERSONS = "persons"
CONF_PERSON_NAME = "name"
CONF_PERSON_ENTITY_ID = "person_entity_id"
CONF_SLUG = "slug"
CONF_RULES = "rules"
CONF_WAKE_WINDOW_MINUTES = "wake_window_minutes"
CONF_HOLIDAY_CALENDAR_ENTITY_ID = "holiday_calendar_entity_id"
CONF_HOLIDAY_BEHAVIOR = "holiday_behavior"
CONF_MANUAL_HOLIDAY_DATES = "manual_holiday_dates"
CONF_CALENDAR_ENTITY_ID = "calendar_entity_id"
CONF_CALENDAR_WAKE_PATTERN = "calendar_wake_pattern"
CONF_CALENDAR_SKIP_TITLES = "calendar_skip_titles"

DEFAULT_WAKE_TIME = "07:00"
DEFAULT_WAKE_WINDOW_MINUTES = 5
DEFAULT_CALENDAR_WAKE_PATTERN = r"(?:wake:\s*)?(?P<time>[0-2]?\d:[0-5]\d)"
DEFAULT_CALENDAR_SKIP_TITLES = "no-wake,schlaf aus"

HOLIDAY_SKIP = "skip"
HOLIDAY_WEEKEND_PROFILE = "weekend_profile"

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKEND_DAYS = {"saturday", "sunday"}

# Service-Aktionen — registriert als `bennis_toolbox.wake_planner_<action>`.
SERVICE_SKIP_NEXT = "skip_next"
SERVICE_SET_OVERRIDE = "set_override"
SERVICE_CLEAR_OVERRIDE = "clear_override"
SERVICE_SET_SPECIAL_RULES = "set_special_rules"
SERVICE_ADD_PERSON = "add_person"
SERVICE_REMOVE_PERSON = "remove_person"
SERVICE_SET_RULES = "set_rules"

ATTR_DECIDED_BY = "decided_by"
ATTR_REASON = "reason"
ATTR_WAKE_TIME = "wake_time"

# Event auf dem HA-Bus, wenn das Wake-Fenster eines Slugs öffnet.
EVENT_WAKE_TRIGGERED = "bennis_toolbox_wake_planner_wake_triggered"


class WakeState(StrEnum):
    SCHEDULED = "scheduled"
    SKIPPED = "skipped"
    OVERRIDDEN = "overridden"
    HOLIDAY = "holiday"
    INACTIVE = "inactive"


RULE_ACTION_WAKE = "wake"
RULE_ACTION_SKIP = "skip"


@dataclass(slots=True)
class Rule:
    id: str
    name: str
    priority: int = 100
    enabled: bool = True
    weekdays: set[int] | None = None
    date_from: date | None = None
    date_to: date | None = None
    week_interval: int | None = None
    week_anchor: date | None = None
    specific_dates: list[date] | None = None
    cycle_anchor: date | None = None
    cycle_length: int | None = None
    cycle_slot_start: int | None = None
    cycle_slot_length: int | None = None
    on_holiday: bool | None = None
    action: str = RULE_ACTION_WAKE
    wake_time: time | None = None


@dataclass(slots=True)
class PersonConfig:
    slug: str
    name: str
    person_entity_id: str | None
    rules: list[Rule] = field(default_factory=list)
    wake_window_minutes: int = DEFAULT_WAKE_WINDOW_MINUTES


@dataclass(slots=True)
class CalendarDecision:
    wake_time: time | None = None
    skip: bool = False
    summary: str | None = None
    source: str = "not_configured"


@dataclass(slots=True)
class WakeDecision:
    wake_time: time | None
    state: WakeState
    decided_by: str
    reason: str
    holiday_name: str | None = None
    skip_active: bool = False
    override_until: date | None = None
    next_wake: datetime | None = None
    wake_window_start: datetime | None = None
    wake_window_end: datetime | None = None
    matched_rule_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "wake_time": self.wake_time.strftime("%H:%M") if self.wake_time else None,
            "state": self.state.value,
            "decided_by": self.decided_by,
            "reason": self.reason,
            "holiday_name": self.holiday_name,
            "skip_active": self.skip_active,
            "override_until": self.override_until.isoformat() if self.override_until else None,
            "next_wake": self.next_wake.isoformat() if self.next_wake else None,
            "wake_window_start": self.wake_window_start.isoformat() if self.wake_window_start else None,
            "wake_window_end": self.wake_window_end.isoformat() if self.wake_window_end else None,
            "matched_rule_id": self.matched_rule_id,
        }


@dataclass(slots=True)
class RuntimePersonState:
    skip_next: bool = False
    override_time: time | None = None
    override_until: date | None = None
