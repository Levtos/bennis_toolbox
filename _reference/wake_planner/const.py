"""Constants and data models for Wake Planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any

DOMAIN = "wake_planner"
NAME = "Wake Planner"
PLATFORMS = ["sensor", "binary_sensor"]

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
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.state"

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

EVENT_WAKE_TRIGGERED = f"{DOMAIN}_wake_triggered"


class WakeState(StrEnum):
    """Supported wake decision states."""

    SCHEDULED = "scheduled"
    SKIPPED = "skipped"
    OVERRIDDEN = "overridden"
    HOLIDAY = "holiday"
    INACTIVE = "inactive"


# --- Rule model -------------------------------------------------------------

RULE_ACTION_WAKE = "wake"
RULE_ACTION_SKIP = "skip"


@dataclass(slots=True)
class Rule:
    """A single wake rule. Conditions AND together; first matching rule wins."""

    id: str
    name: str
    priority: int = 100  # lower = evaluated first
    enabled: bool = True

    # Conditions (all that are set must match; unset = ignored)
    weekdays: set[int] | None = None              # 0=Mon..6=Sun
    date_from: date | None = None                 # inclusive
    date_to: date | None = None                   # inclusive
    week_interval: int | None = None              # every Nth ISO week
    week_anchor: date | None = None               # any date within reference week
    specific_dates: list[date] | None = None      # one-off matches
    cycle_anchor: date | None = None              # shift cycles
    cycle_length: int | None = None               # total days in cycle
    cycle_slot_start: int | None = None           # 0-indexed start day in cycle
    cycle_slot_length: int | None = None          # number of consecutive days
    on_holiday: bool | None = None                # True = only holidays, False = only non-holidays

    # Action
    action: str = RULE_ACTION_WAKE                # "wake" | "skip"
    wake_time: time | None = None                 # required when action="wake"


@dataclass(slots=True)
class PersonConfig:
    """Configured wake planner person."""

    slug: str
    name: str
    person_entity_id: str | None
    rules: list[Rule] = field(default_factory=list)
    wake_window_minutes: int = DEFAULT_WAKE_WINDOW_MINUTES


@dataclass(slots=True)
class CalendarDecision:
    """Calendar-derived wake instruction for a day."""

    wake_time: time | None = None
    skip: bool = False
    summary: str | None = None
    source: str = "not_configured"


@dataclass(slots=True)
class WakeDecision:
    """Result of evaluating the rule engine."""

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
        """Return a JSON-serialisable representation."""
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
    """Persisted runtime state for one person."""

    skip_next: bool = False
    override_time: time | None = None
    override_until: date | None = None
