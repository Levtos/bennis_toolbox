"""Utility helpers for Wake Planner."""

from __future__ import annotations

from datetime import date
import uuid
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_PERSON_ENTITY_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    CONF_CALENDAR_CONFLICT_BEHAVIOR,
    CONF_ROUTINE_DURATION_MINUTES,
    CONF_RULES,
    CONF_SLUG,
    CONF_WAKE_WINDOW_MINUTES,
    CONFLICT_BEHAVIORS,
    CONFLICT_WARN_ONLY,
    DEFAULT_ROUTINE_DURATION_MINUTES,
    DEFAULT_WEEKEND_WAKE_TIME,
    DAYS,
    DEFAULT_WAKE_TIME,
    DEFAULT_WAKE_WINDOW_MINUTES,
    RULE_ACTION_SKIP,
    RULE_ACTION_WAKE,
    PersonConfig,
    Rule,
)
from .rule_engine import parse_date, parse_time

_WEEKDAY_INDEX = {day: i for i, day in enumerate(DAYS)}


def default_rules() -> list[dict[str, Any]]:
    """Return the standard wake profile rules for new persons."""
    return [
        {
            "id": "profile_weekday",
            "name": "Werktage",
            "priority": 100,
            "enabled": True,
            "weekdays": [0, 1, 2, 3, 4],
            "on_holiday": False,
            "action": RULE_ACTION_WAKE,
            "wake_time": DEFAULT_WAKE_TIME,
        },
        {
            "id": "profile_weekend",
            "name": "Wochenende",
            "priority": 110,
            "enabled": True,
            "weekdays": [5, 6],
            "on_holiday": None,
            "action": RULE_ACTION_WAKE,
            "wake_time": DEFAULT_WEEKEND_WAKE_TIME,
        },
        {
            "id": "profile_holiday",
            "name": "Feiertage",
            "priority": 90,
            "enabled": True,
            "weekdays": [0, 1, 2, 3, 4],
            "on_holiday": True,
            "action": RULE_ACTION_WAKE,
            "wake_time": DEFAULT_WEEKEND_WAKE_TIME,
        },
    ]


def _parse_rule(raw: dict[str, Any]) -> Rule | None:
    """Convert a stored dict to a Rule, skipping malformed entries."""
    try:
        action = raw.get("action") or RULE_ACTION_WAKE
        wake_time_raw = raw.get("wake_time")
        wake_time = parse_time(str(wake_time_raw)) if wake_time_raw else None
        if action == RULE_ACTION_WAKE and wake_time is None:
            return None
        weekdays = raw.get("weekdays")
        if weekdays is not None:
            weekdays = {int(w) for w in weekdays if 0 <= int(w) <= 6}
            if not weekdays:
                weekdays = None
        specific = raw.get("specific_dates")
        if specific is not None:
            parsed = [parse_date(str(d)) for d in specific]
            specific = [d for d in parsed if d is not None] or None
        return Rule(
            id=str(raw.get("id") or uuid.uuid4()),
            name=str(raw.get("name") or "Rule"),
            priority=int(raw.get("priority", 100)),
            enabled=bool(raw.get("enabled", True)),
            weekdays=weekdays,
            date_from=parse_date(raw.get("date_from")),
            date_to=parse_date(raw.get("date_to")),
            week_interval=int(raw["week_interval"]) if raw.get("week_interval") else None,
            week_anchor=parse_date(raw.get("week_anchor")),
            specific_dates=specific,
            cycle_anchor=parse_date(raw.get("cycle_anchor")),
            cycle_length=int(raw["cycle_length"]) if raw.get("cycle_length") else None,
            cycle_slot_start=int(raw["cycle_slot_start"]) if raw.get("cycle_slot_start") is not None else None,
            cycle_slot_length=int(raw["cycle_slot_length"]) if raw.get("cycle_slot_length") else None,
            on_holiday=bool(raw["on_holiday"]) if raw.get("on_holiday") is not None and raw.get("on_holiday") != "" else None,
            action=action,
            wake_time=wake_time,
        )
    except (ValueError, TypeError, KeyError):
        return None


def rule_to_dict(rule: Rule) -> dict[str, Any]:
    """Serialise a Rule back to its storage dict form."""
    return {
        "id": rule.id,
        "name": rule.name,
        "priority": rule.priority,
        "enabled": rule.enabled,
        "weekdays": sorted(rule.weekdays) if rule.weekdays else None,
        "date_from": rule.date_from.isoformat() if rule.date_from else None,
        "date_to": rule.date_to.isoformat() if rule.date_to else None,
        "week_interval": rule.week_interval,
        "week_anchor": rule.week_anchor.isoformat() if rule.week_anchor else None,
        "specific_dates": [d.isoformat() for d in rule.specific_dates] if rule.specific_dates else None,
        "cycle_anchor": rule.cycle_anchor.isoformat() if rule.cycle_anchor else None,
        "cycle_length": rule.cycle_length,
        "cycle_slot_start": rule.cycle_slot_start,
        "cycle_slot_length": rule.cycle_slot_length,
        "on_holiday": rule.on_holiday,
        "action": rule.action,
        "wake_time": rule.wake_time.strftime("%H:%M") if rule.wake_time else None,
    }


def migrate_legacy_person(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert old weekly_profile / shift_cycle stored data into rules.

    Returns the same dict augmented with a `rules` list when the legacy
    fields are present and no rules exist yet.
    """
    if raw.get(CONF_RULES):
        return raw

    rules: list[dict[str, Any]] = []
    weekly = raw.get("weekly_profile")
    shift = raw.get("shift_cycle")

    if shift and shift.get("slots") and shift.get("anchor_date"):
        try:
            anchor = parse_date(shift["anchor_date"])
        except ValueError:
            anchor = None
        slots = shift.get("slots") or []
        total = sum(int(s.get("duration_days", 0)) for s in slots)
        offset = 0
        if anchor and total > 0:
            for slot in slots:
                length = int(slot.get("duration_days", 0))
                if length <= 0:
                    continue
                slot_weekly = slot.get("weekly_profile") or {}
                for day_name, day_data in slot_weekly.items():
                    if not day_data.get("active"):
                        continue
                    idx = _WEEKDAY_INDEX.get(day_name)
                    if idx is None:
                        continue
                    rules.append({
                        "id": str(uuid.uuid4()),
                        "name": f"{slot.get('slot_name') or slot.get('name') or 'Shift'} · {day_name[:3].title()}",
                        "priority": 50,
                        "enabled": True,
                        "weekdays": [idx],
                        "cycle_anchor": anchor.isoformat(),
                        "cycle_length": total,
                        "cycle_slot_start": offset,
                        "cycle_slot_length": length,
                        "action": RULE_ACTION_WAKE,
                        "wake_time": day_data.get("wake_time") or DEFAULT_WAKE_TIME,
                    })
                offset += length
    elif weekly:
        for day_name, day_data in weekly.items():
            idx = _WEEKDAY_INDEX.get(day_name)
            if idx is None or not day_data.get("active"):
                continue
            rules.append({
                "id": str(uuid.uuid4()),
                "name": day_name.title(),
                "priority": 100,
                "enabled": True,
                "weekdays": [idx],
                "action": RULE_ACTION_WAKE,
                "wake_time": day_data.get("wake_time") or DEFAULT_WAKE_TIME,
            })

    if not rules:
        rules = default_rules()

    raw = dict(raw)
    raw[CONF_RULES] = rules
    return raw


def persons_from_entry(entry: ConfigEntry) -> list[PersonConfig]:
    """Build PersonConfig objects from a config entry, migrating legacy data."""
    raw_persons = (entry.options or {}).get(CONF_PERSONS) or entry.data.get(CONF_PERSONS) or []
    persons: list[PersonConfig] = []
    for raw in raw_persons:
        raw = migrate_legacy_person(raw)
        rules = [r for r in (_parse_rule(item) for item in raw.get(CONF_RULES, [])) if r is not None]
        persons.append(
            PersonConfig(
                slug=raw[CONF_SLUG],
                name=raw[CONF_PERSON_NAME],
                person_entity_id=raw.get(CONF_PERSON_ENTITY_ID),
                rules=rules,
                wake_window_minutes=int(raw.get(CONF_WAKE_WINDOW_MINUTES, DEFAULT_WAKE_WINDOW_MINUTES)),
                routine_duration_minutes=int(
                    raw.get(CONF_ROUTINE_DURATION_MINUTES, DEFAULT_ROUTINE_DURATION_MINUTES)
                ),
                calendar_conflict_behavior=(
                    raw.get(CONF_CALENDAR_CONFLICT_BEHAVIOR)
                    if raw.get(CONF_CALENDAR_CONFLICT_BEHAVIOR) in CONFLICT_BEHAVIORS
                    else CONFLICT_WARN_ONLY
                ),
            )
        )
    return persons
