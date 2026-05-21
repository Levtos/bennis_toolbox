"""Unit tests for the Wake Planner rule engine — HA-free."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest

import wp_const as C
import wp_rule_engine as RE


# ---------------------------------------------------------------------- parse


def test_parse_time_accepts_hhmm():
    assert RE.parse_time("07:30") == time(7, 30)
    assert RE.parse_time("23:59") == time(23, 59)
    assert RE.parse_time("07:30:00") == time(7, 30)


@pytest.mark.parametrize("bad", ["", "7", "07", "07:60", "24:00", "abc"])
def test_parse_time_rejects_bad(bad: str):
    with pytest.raises(ValueError):
        RE.parse_time(bad)


def test_parse_date_passthrough_and_none():
    assert RE.parse_date(None) is None
    assert RE.parse_date("") is None
    assert RE.parse_date("2026-01-15") == date(2026, 1, 15)


# ---------------------------------------------------------------------- rules


def _wake_rule(**overrides):
    base = dict(
        id="r1",
        name="Weekdays",
        priority=100,
        enabled=True,
        weekdays={0, 1, 2, 3, 4},
        action=C.RULE_ACTION_WAKE,
        wake_time=time(7, 0),
    )
    base.update(overrides)
    return C.Rule(**base)


def test_rule_matches_weekday():
    rule = _wake_rule()
    # 2026-01-12 is a Monday
    assert RE.rule_matches(rule, date(2026, 1, 12))
    # Saturday
    assert not RE.rule_matches(rule, date(2026, 1, 17))


def test_rule_matches_disabled():
    rule = _wake_rule(enabled=False)
    assert not RE.rule_matches(rule, date(2026, 1, 12))


def test_rule_matches_date_range():
    rule = _wake_rule(weekdays=None, date_from=date(2026, 1, 10), date_to=date(2026, 1, 12))
    assert RE.rule_matches(rule, date(2026, 1, 11))
    assert not RE.rule_matches(rule, date(2026, 1, 13))


def test_rule_matches_on_holiday_flag():
    rule = _wake_rule(on_holiday=True)
    assert RE.rule_matches(rule, date(2026, 1, 12), is_holiday=True)
    assert not RE.rule_matches(rule, date(2026, 1, 12), is_holiday=False)


def test_rule_matches_specific_dates():
    rule = _wake_rule(weekdays=None, specific_dates=[date(2026, 3, 14)])
    assert RE.rule_matches(rule, date(2026, 3, 14))
    assert not RE.rule_matches(rule, date(2026, 3, 15))


def test_rule_matches_cycle():
    # 6-day cycle anchored on 2026-01-05 (Monday), wake on days 0..1 (Mon/Tue of cycle).
    rule = _wake_rule(
        weekdays=None,
        cycle_anchor=date(2026, 1, 5),
        cycle_length=6,
        cycle_slot_start=0,
        cycle_slot_length=2,
    )
    assert RE.rule_matches(rule, date(2026, 1, 5))
    assert RE.rule_matches(rule, date(2026, 1, 6))
    assert not RE.rule_matches(rule, date(2026, 1, 7))
    # Next cycle iteration on 2026-01-11 (Sunday in absolute calendar — but slot starts again on day 0)
    assert RE.rule_matches(rule, date(2026, 1, 11))


# --------------------------------------------------------------------- engine


def _engine(holiday=False, holiday_behavior=C.HOLIDAY_SKIP, calendar_decisions=None):
    holiday_map = {date(2026, 1, 12): (True, "Test holiday")} if holiday else {}
    return RE.RuleEngine(
        runtime_states={},
        calendar_decisions=calendar_decisions or {},
        holiday_by_date=holiday_map,
        holiday_behavior=holiday_behavior,
    )


def _person(rules=None):
    return C.PersonConfig(
        slug="p1",
        name="Person 1",
        person_entity_id=None,
        rules=rules or [_wake_rule()],
        wake_window_minutes=5,
    )


def test_engine_scheduled_weekday():
    engine = _engine()
    now = datetime(2026, 1, 12, 6, 0, tzinfo=timezone.utc)  # Monday before wake
    decision = engine.decide(_person(), now)
    assert decision.state == C.WakeState.SCHEDULED
    assert decision.wake_time == time(7, 0)
    assert decision.wake_window_start is not None
    assert decision.wake_window_end is not None


def test_engine_holiday_skip_default():
    # Person has no rule that matches Monday → holiday fallback decides.
    weekend_only = _wake_rule(weekdays={5, 6})
    engine = _engine(holiday=True)
    now = datetime(2026, 1, 12, 6, 0, tzinfo=timezone.utc)
    decision = engine.decide(_person([weekend_only]), now)
    assert decision.state == C.WakeState.HOLIDAY
    assert decision.wake_time is None


def test_engine_holiday_weekend_profile_uses_saturday_rule():
    # No matching weekday rule → weekend_profile uses Saturday rule.
    saturday_rule = _wake_rule(
        id="rs", name="Weekend", weekdays={5, 6}, wake_time=time(9, 0)
    )
    engine = _engine(holiday=True, holiday_behavior=C.HOLIDAY_WEEKEND_PROFILE)
    now = datetime(2026, 1, 12, 6, 0, tzinfo=timezone.utc)
    decision = engine.decide(_person([saturday_rule]), now)
    assert decision.state == C.WakeState.SCHEDULED
    assert decision.wake_time == time(9, 0)
    assert decision.matched_rule_id == "rs"


def test_engine_holiday_does_not_match_non_holiday_weekday_rule():
    weekday_non_holiday = _wake_rule(on_holiday=False)
    weekend_rule = _wake_rule(
        id="rw", name="Weekend", weekdays={5, 6}, wake_time=time(9, 30), on_holiday=None
    )
    engine = _engine(holiday=True)
    now = datetime(2026, 1, 12, 6, 0, tzinfo=timezone.utc)
    decision = engine.decide(_person([weekday_non_holiday, weekend_rule]), now)
    assert decision.state == C.WakeState.HOLIDAY
    assert decision.wake_time is None


def test_engine_holiday_weekend_profile_ignores_non_holiday_weekday_rule():
    weekday_non_holiday = _wake_rule(on_holiday=False)
    weekend_rule = _wake_rule(
        id="rw", name="Weekend", weekdays={5, 6}, wake_time=time(9, 30), on_holiday=None
    )
    engine = _engine(holiday=True, holiday_behavior=C.HOLIDAY_WEEKEND_PROFILE)
    now = datetime(2026, 1, 12, 6, 0, tzinfo=timezone.utc)
    decision = engine.decide(_person([weekday_non_holiday, weekend_rule]), now)
    assert decision.state == C.WakeState.SCHEDULED
    assert decision.wake_time == time(9, 30)
    assert decision.matched_rule_id == "rw"


def test_engine_profile_holiday_rule_only_replaces_weekday_holidays():
    weekday = _wake_rule(id="profile_weekday", on_holiday=False)
    weekend = _wake_rule(
        id="profile_weekend",
        name="Weekend",
        weekdays={5, 6},
        wake_time=time(9, 30),
        on_holiday=None,
    )
    holiday = _wake_rule(
        id="profile_holiday",
        name="Holiday",
        weekdays={0, 1, 2, 3, 4},
        wake_time=time(9, 30),
        on_holiday=True,
        priority=90,
    )
    engine = _engine(holiday=True)
    monday = datetime(2026, 1, 12, 6, 0, tzinfo=timezone.utc)
    monday_decision = engine.decide(_person([weekday, weekend, holiday]), monday)
    assert monday_decision.wake_time == time(9, 30)
    assert monday_decision.matched_rule_id == "profile_holiday"

    assert RE.rule_matches(weekend, date(2026, 1, 17), is_holiday=True)
    assert not RE.rule_matches(holiday, date(2026, 1, 17), is_holiday=True)


def test_engine_one_day_exception_overrides_profile():
    weekday = _wake_rule(id="profile_weekday", on_holiday=False)
    exception = _wake_rule(
        id="exception_late",
        name="Ausnahme",
        priority=20,
        weekdays=None,
        specific_dates=[date(2026, 1, 12)],
        wake_time=time(8, 0),
        on_holiday=None,
    )
    engine = _engine()
    now = datetime(2026, 1, 12, 6, 0, tzinfo=timezone.utc)
    decision = engine.decide(_person([weekday, exception]), now)
    assert decision.wake_time == time(8, 0)
    assert decision.matched_rule_id == "exception_late"


def test_engine_exception_range_can_skip_profile():
    weekday = _wake_rule(id="profile_weekday", on_holiday=False)
    exception = C.Rule(
        id="exception_vacation",
        name="Urlaub",
        priority=20,
        enabled=True,
        weekdays=None,
        date_from=date(2026, 1, 12),
        date_to=date(2026, 1, 16),
        action=C.RULE_ACTION_SKIP,
        wake_time=None,
    )
    engine = _engine()
    now = datetime(2026, 1, 14, 6, 0, tzinfo=timezone.utc)
    decision = engine.decide(_person([weekday, exception]), now)
    assert decision.state == C.WakeState.SKIPPED
    assert decision.matched_rule_id == "exception_vacation"


def test_engine_skip_action():
    skip_rule = C.Rule(
        id="r2", name="No-go", priority=10, enabled=True,
        weekdays={0, 1, 2, 3, 4},
        action=C.RULE_ACTION_SKIP, wake_time=None,
    )
    engine = _engine()
    now = datetime(2026, 1, 12, 6, 0, tzinfo=timezone.utc)
    decision = engine.decide(_person([skip_rule, _wake_rule()]), now)
    assert decision.state == C.WakeState.SKIPPED
    assert decision.matched_rule_id == "r2"


def test_engine_manual_skip_next():
    person = _person()
    engine = _engine()
    engine._runtime_states[person.slug] = C.RuntimePersonState(skip_next=True)
    now = datetime(2026, 1, 12, 6, 0, tzinfo=timezone.utc)
    decision = engine.decide(person, now)
    assert decision.state == C.WakeState.SKIPPED
    assert decision.decided_by == "override"


def test_engine_override_active():
    person = _person()
    engine = _engine()
    engine._runtime_states[person.slug] = C.RuntimePersonState(
        override_time=time(5, 30),
        override_until=date(2026, 1, 12),
    )
    now = datetime(2026, 1, 12, 4, 0, tzinfo=timezone.utc)
    decision = engine.decide(person, now)
    assert decision.state == C.WakeState.OVERRIDDEN
    assert decision.wake_time == time(5, 30)


def test_engine_warns_when_early_calendar_event_conflicts_with_routine():
    person = _person()
    calendar = {
        (person.slug, date(2026, 1, 12)): C.CalendarDecision(
            early_event_time=time(6, 30),
            summary="Früher Termin",
            source="calendar",
        )
    }
    engine = _engine(calendar_decisions=calendar)
    now = datetime(2026, 1, 12, 5, 0, tzinfo=timezone.utc)
    decision = engine.decide(person, now)
    assert decision.wake_time == time(7, 0)
    assert decision.calendar_conflict_time == time(6, 30)
    assert decision.calendar_suggested_wake_time == time(5, 30)


def test_engine_can_wake_earlier_for_calendar_conflict():
    person = C.PersonConfig(
        slug="p1",
        name="Person 1",
        person_entity_id=None,
        rules=[_wake_rule()],
        routine_duration_minutes=60,
        calendar_conflict_behavior=C.CONFLICT_WAKE_EARLIER,
    )
    calendar = {
        (person.slug, date(2026, 1, 12)): C.CalendarDecision(
            early_event_time=time(6, 30),
            summary="Früher Termin",
            source="calendar",
        )
    }
    engine = _engine(calendar_decisions=calendar)
    now = datetime(2026, 1, 12, 5, 0, tzinfo=timezone.utc)
    decision = engine.decide(person, now)
    assert decision.wake_time == time(5, 30)
    assert decision.decided_by == "calendar_conflict"


def test_engine_next_wake_skips_holidays():
    # Weekend-only rule + holiday on Monday → next_wake jumps to Saturday
    # because nothing matches Mon-Fri.
    weekend_only = _wake_rule(weekdays={5, 6})
    engine = _engine(holiday=True)
    now = datetime(2026, 1, 12, 6, 0, tzinfo=timezone.utc)  # Monday
    nxt = engine.next_wake(_person([weekend_only]), now)
    assert nxt is not None
    assert nxt.date() == date(2026, 1, 17)  # Saturday


def test_engine_no_rule_yields_inactive():
    engine = _engine()
    now = datetime(2026, 1, 17, 6, 0, tzinfo=timezone.utc)  # Saturday, weekday rule only
    decision = engine.decide(_person(), now)
    assert decision.state == C.WakeState.INACTIVE
