"""Wake Planner exposes a holiday-active binary sensor.

This is the clean boolean projection that `benni_context.holiday_sensor`
consumes. Truth table:
- `decision.holiday_name` non-empty            → on
- `decision.matched_rule_id == "profile_holiday"` → on
- regular weekday plan                         → off
- no decision at all                           → off

Plus the usual contract: stable `unique_id`, readable
`suggested_object_id`, the requested attribute set.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest


# Reuse the heavy stub setup from test_entity_outputs — that file
# already loads the real entities.py with the HA stubs and the
# synthetic toolbox package.
from tests.wake_planner.test_entity_outputs import (  # noqa: E402
    entities,
    wp_const,
    _Person,
    _entry,
)


@dataclass
class _StubDecision:
    """Richer stub than test_entity_outputs._StubDecision — adds the
    holiday / matched-rule / next_wake fields the new sensor consumes."""

    state: object | None = None
    holiday_name: str | None = None
    matched_rule_id: str | None = None
    decided_by: str | None = None
    reason: str | None = None
    next_wake: datetime | None = None
    wake_window_start: datetime | None = None
    wake_window_end: datetime | None = None
    wake_time: str | None = None

    def as_dict(self) -> dict:
        return {
            "state": getattr(self.state, "value", None),
            "holiday_name": self.holiday_name,
            "matched_rule_id": self.matched_rule_id,
            "decided_by": self.decided_by,
            "reason": self.reason,
            "next_wake": self.next_wake.isoformat() if self.next_wake else None,
            "wake_window_start": self.wake_window_start.isoformat() if self.wake_window_start else None,
            "wake_window_end": self.wake_window_end.isoformat() if self.wake_window_end else None,
            "wake_time": self.wake_time,
        }


class _StubCoord:
    def __init__(self, decision=None, slug: str = "benni"):
        self.persons = [_Person(slug=slug, name="Benni")]
        self.data = {slug: decision} if decision else {}
        self.next_wakes = {}
        self.options = {}


# ---------------------------------------------------------------------------
# 1) is_on truth table.
# ---------------------------------------------------------------------------


def test_holiday_active_on_when_holiday_name_set():
    """Wake Planner detected a holiday by name → boolean projection ON."""
    decision = _StubDecision(
        state=wp_const.WakeState.SCHEDULED,
        holiday_name="Pfingstmontag",
        matched_rule_id="profile_holiday",
        decided_by="rule:Feiertage",
        reason="Rule 'Feiertage': 09:30",
    )
    coord = _StubCoord(decision=decision)
    sensor = entities.HolidayActiveBinarySensor(coord, _entry(), coord.persons[0])
    assert sensor.is_on is True


def test_holiday_active_on_when_only_matched_rule_id_set():
    """Holiday detected via profile-holiday rule without a name —
    sensor must still fire ON."""
    decision = _StubDecision(
        state=wp_const.WakeState.SCHEDULED,
        holiday_name=None,
        matched_rule_id="profile_holiday",
        decided_by="rule:profile_holiday",
        reason="Rule 'profile_holiday': 09:30",
    )
    coord = _StubCoord(decision=decision)
    sensor = entities.HolidayActiveBinarySensor(coord, _entry(), coord.persons[0])
    assert sensor.is_on is True


def test_holiday_active_off_on_regular_weekday():
    decision = _StubDecision(
        state=wp_const.WakeState.SCHEDULED,
        holiday_name=None,
        matched_rule_id="profile_weekday",
        decided_by="rule:Werktage",
        reason="Rule 'Werktage': 07:00",
    )
    coord = _StubCoord(decision=decision)
    sensor = entities.HolidayActiveBinarySensor(coord, _entry(), coord.persons[0])
    assert sensor.is_on is False


def test_holiday_active_off_when_decision_missing():
    """Cold-start / coordinator hasn't produced a decision yet → OFF
    (not unknown — the consumer can rely on a clean boolean)."""
    coord = _StubCoord(decision=None)
    sensor = entities.HolidayActiveBinarySensor(coord, _entry(), coord.persons[0])
    assert sensor.is_on is False


def test_holiday_active_off_when_empty_holiday_name_and_other_rule():
    """Defensive: an empty-string holiday_name shouldn't be treated as truthy."""
    decision = _StubDecision(
        state=wp_const.WakeState.SCHEDULED,
        holiday_name="",
        matched_rule_id="profile_weekday",
    )
    coord = _StubCoord(decision=decision)
    sensor = entities.HolidayActiveBinarySensor(coord, _entry(), coord.persons[0])
    assert sensor.is_on is False


# ---------------------------------------------------------------------------
# 2) Attributes surface the diagnostic fields benni_context might want.
# ---------------------------------------------------------------------------


def test_holiday_active_exposes_expected_attributes():
    next_wake = datetime(2026, 5, 25, 9, 30, tzinfo=timezone.utc)
    decision = _StubDecision(
        state=wp_const.WakeState.SCHEDULED,
        holiday_name="Pfingstmontag",
        matched_rule_id="profile_holiday",
        decided_by="rule:Feiertage",
        reason="Rule 'Feiertage': 09:30",
        next_wake=next_wake,
    )
    coord = _StubCoord(decision=decision)
    sensor = entities.HolidayActiveBinarySensor(coord, _entry(), coord.persons[0])
    attrs = sensor.extra_state_attributes
    assert attrs["holiday_name"] == "Pfingstmontag"
    assert attrs["reason"] == "Rule 'Feiertage': 09:30"
    assert attrs["decided_by"] == "rule:Feiertage"
    assert attrs["matched_rule_id"] == "profile_holiday"
    assert attrs["next_wake"] == "2026-05-25T09:30:00+00:00"
    assert attrs["wake_state"] == "scheduled"
    assert attrs["person_id"] == "benni"


def test_holiday_active_attributes_handle_missing_decision():
    coord = _StubCoord(decision=None)
    sensor = entities.HolidayActiveBinarySensor(coord, _entry(), coord.persons[0])
    assert sensor.extra_state_attributes == {}


def test_holiday_active_attributes_handle_missing_next_wake():
    decision = _StubDecision(
        state=wp_const.WakeState.SCHEDULED,
        holiday_name="Pfingstmontag",
        next_wake=None,
    )
    coord = _StubCoord(decision=decision)
    sensor = entities.HolidayActiveBinarySensor(coord, _entry(), coord.persons[0])
    assert sensor.extra_state_attributes["next_wake"] is None


# ---------------------------------------------------------------------------
# 3) ID contract — suggested_object_id readable, unique_id stable.
# ---------------------------------------------------------------------------


def test_holiday_active_suggested_object_id_is_readable():
    coord = _StubCoord(decision=None)
    sensor = entities.HolidayActiveBinarySensor(coord, _entry(), coord.persons[0])
    assert sensor._attr_suggested_object_id == "wake_planner_benni_holiday_active"


def test_holiday_active_unique_id_follows_existing_wake_planner_pattern():
    coord = _StubCoord(decision=None)
    sensor = entities.HolidayActiveBinarySensor(coord, _entry(), coord.persons[0])
    assert sensor._attr_unique_id == (
        "bennis_toolbox_wake_planner_entry-1_benni_holiday_active"
    )


# ---------------------------------------------------------------------------
# 4) Platform registration includes the new sensor.
# ---------------------------------------------------------------------------


def test_async_get_entities_returns_both_binary_sensors_per_person():
    """The platform dispatcher must yield both `WakeNeededBinarySensor`
    AND `HolidayActiveBinarySensor` for every configured person."""
    import asyncio

    class _MultiCoord(_StubCoord):
        def __init__(self):
            self.persons = [
                _Person(slug="benni", name="Benni"),
                _Person(slug="other", name="Other"),
            ]
            self.data = {}
            self.next_wakes = {}
            self.options = {}

    # async_get_entities accepts a `hass` argument that we don't use
    # in stub mode, so a plain object suffices.
    hass = object()
    entry = _entry()
    # Patch the module-level `coordinator_from_hass` to return our
    # stub coordinator.
    import sys
    sys.modules[entities.__name__].coordinator_from_hass = (
        lambda hass, entry_id: _MultiCoord()
    )

    # The Platform enum in the stub layer maps SENSOR / BINARY_SENSOR
    # to plain strings; reuse the same.
    import homeassistant.const as hc
    out = asyncio.run(
        entities.async_get_entities(hass, entry, hc.Platform.BINARY_SENSOR)
    )
    # Two persons × two binary sensors = four entities.
    assert len(out) == 4
    classes = {type(e).__name__ for e in out}
    assert classes == {"WakeNeededBinarySensor", "HolidayActiveBinarySensor"}
    by_slug: dict[str, set[str]] = {}
    for e in out:
        by_slug.setdefault(e.person.slug, set()).add(type(e).__name__)
    for slug in ("benni", "other"):
        assert by_slug[slug] == {"WakeNeededBinarySensor", "HolidayActiveBinarySensor"}, slug
