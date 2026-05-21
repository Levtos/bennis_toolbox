"""Rule evaluation for Wake Planner."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import logging

from .const import (
    CONFLICT_IGNORE,
    CONFLICT_WAKE_EARLIER,
    CONFLICT_WARN_ONLY,
    HOLIDAY_SKIP,
    HOLIDAY_WEEKEND_PROFILE,
    RULE_ACTION_SKIP,
    RULE_ACTION_WAKE,
    CalendarDecision,
    PersonConfig,
    Rule,
    RuntimePersonState,
    WakeDecision,
    WakeState,
)

_LOGGER = logging.getLogger(__name__)


def parse_time(value: str) -> time:
    """Parse a HH:MM or HH:MM:SS time string."""
    parts = value.strip().split(":")
    if len(parts) not in (2, 3):
        raise ValueError("time must be in HH:MM format")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("hour 0-23, minute 0-59")
    return time(hour, minute)


def parse_date(value: str | None) -> date | None:
    """Parse an ISO date string when present."""
    if not value:
        return None
    return date.fromisoformat(value)


def format_time(value: time | None) -> str | None:
    """Format a time for entity state/attributes."""
    return value.strftime("%H:%M") if value else None


def rule_matches(rule: Rule, day: date, is_holiday: bool = False) -> bool:
    """Return true if all set conditions on the rule match the given date."""
    if not rule.enabled:
        return False
    if rule.on_holiday is not None and bool(is_holiday) != rule.on_holiday:
        return False
    if rule.weekdays is not None and day.weekday() not in rule.weekdays:
        return False
    if rule.date_from is not None and day < rule.date_from:
        return False
    if rule.date_to is not None and day > rule.date_to:
        return False
    if rule.specific_dates is not None and day not in rule.specific_dates:
        return False
    if rule.week_interval is not None and rule.week_anchor is not None and rule.week_interval > 0:
        day_week_start = day - timedelta(days=day.weekday())
        anchor_week_start = rule.week_anchor - timedelta(days=rule.week_anchor.weekday())
        weeks_since = (day_week_start - anchor_week_start).days // 7
        if weeks_since < 0 or weeks_since % rule.week_interval != 0:
            return False
    if (
        rule.cycle_anchor is not None
        and rule.cycle_length is not None
        and rule.cycle_slot_start is not None
        and rule.cycle_slot_length is not None
        and rule.cycle_length > 0
    ):
        offset = (day - rule.cycle_anchor).days % rule.cycle_length
        if offset < rule.cycle_slot_start or offset >= rule.cycle_slot_start + rule.cycle_slot_length:
            return False
    return True


class RuleEngine:
    """Evaluate manual overrides, calendar/holiday gates and the person's rules."""

    def __init__(
        self,
        *,
        runtime_states: dict[str, RuntimePersonState],
        calendar_decisions: dict[tuple[str, date], CalendarDecision],
        holiday_by_date: dict[date, tuple[bool, str | None]],
        holiday_behavior: str,
    ) -> None:
        self._runtime_states = runtime_states
        self._calendar_decisions = calendar_decisions
        self._holiday_by_date = holiday_by_date
        self._holiday_behavior = holiday_behavior

    def decide(self, person: PersonConfig, now: datetime) -> WakeDecision:
        """Decide whether and when a person should wake today."""
        return self._decide_for_date(person, now.date(), now)

    def next_wake(self, person: PersonConfig, now: datetime, days: int = 30) -> datetime | None:
        """Find the next scheduled or overridden wake datetime within `days`."""
        for offset in range(days + 1):
            candidate_date = now.date() + timedelta(days=offset)
            decision = self._decide_for_date(person, candidate_date, now)
            if decision.wake_time is None or decision.state in {WakeState.SKIPPED, WakeState.HOLIDAY, WakeState.INACTIVE}:
                continue
            candidate = datetime.combine(candidate_date, decision.wake_time, tzinfo=now.tzinfo)
            if candidate >= now:
                return candidate
        return None

    # ------------------------------------------------------------------ core

    def _decide_for_date(self, person: PersonConfig, day: date, now: datetime) -> WakeDecision:
        runtime = self._runtime_states.setdefault(person.slug, RuntimePersonState())

        active_override = runtime.override_time is not None and (
            runtime.override_until is None or runtime.override_until >= day
        )
        if active_override:
            return self._build(
                person, day, runtime.override_time, now.tzinfo,
                WakeState.OVERRIDDEN, "override",
                f"Manual override: {runtime.override_time.strftime('%H:%M')}",
                skip_active=runtime.skip_next,
                override_until=runtime.override_until,
            )

        if runtime.skip_next and day == now.date():
            return WakeDecision(
                wake_time=None, state=WakeState.SKIPPED, decided_by="override",
                reason="Next wake skipped manually", skip_active=True,
            )

        calendar = self._calendar_decisions.get((person.slug, day))
        if calendar and calendar.skip:
            return WakeDecision(
                wake_time=None, state=WakeState.SKIPPED, decided_by="calendar",
                reason=f"Calendar skip: {calendar.summary or 'all-day'}",
                skip_active=runtime.skip_next,
            )
        if calendar and calendar.wake_time:
            return self._build(
                person, day, calendar.wake_time, now.tzinfo,
                WakeState.SCHEDULED, "calendar",
                f"Calendar event: {calendar.summary or calendar.wake_time.strftime('%H:%M')}",
                skip_active=runtime.skip_next,
            )

        is_holiday, holiday_name = self._holiday_by_date.get(day, (False, None))

        matched = self._match_rule(person, day, is_holiday)
        if matched is None:
            # Fallback: a holiday with no rule explicitly handling it
            if is_holiday:
                if self._holiday_behavior == HOLIDAY_WEEKEND_PROFILE:
                    saturday_rule = self._first_saturday_rule(person)
                    if saturday_rule and saturday_rule.wake_time:
                        return self._build(
                            person, day, saturday_rule.wake_time, now.tzinfo,
                            WakeState.SCHEDULED, "holiday_fallback",
                            f"Holiday → using Saturday rule '{saturday_rule.name}'",
                            holiday_name=holiday_name, skip_active=runtime.skip_next,
                            matched_rule_id=saturday_rule.id,
                        )
                return WakeDecision(
                    wake_time=None, state=WakeState.HOLIDAY, decided_by="holiday",
                    reason=holiday_name or "Holiday/weekend",
                    holiday_name=holiday_name, skip_active=runtime.skip_next,
                )
            return WakeDecision(
                wake_time=None, state=WakeState.INACTIVE, decided_by="no_rule",
                reason="No matching rule",
                holiday_name=holiday_name, skip_active=runtime.skip_next,
            )

        if matched.action == RULE_ACTION_SKIP:
            return WakeDecision(
                wake_time=None, state=WakeState.SKIPPED, decided_by=f"rule:{matched.name}",
                reason=f"Rule '{matched.name}' skips this day",
                holiday_name=holiday_name, skip_active=runtime.skip_next,
                matched_rule_id=matched.id,
            )

        decision = self._build(
            person, day, matched.wake_time, now.tzinfo,
            WakeState.SCHEDULED, f"rule:{matched.name}",
            f"Rule '{matched.name}': {matched.wake_time.strftime('%H:%M') if matched.wake_time else ''}",
            holiday_name=holiday_name, skip_active=runtime.skip_next,
            matched_rule_id=matched.id,
        )
        return self._apply_calendar_conflict(person, day, now, decision, calendar)

    def _match_rule(self, person: PersonConfig, day: date, is_holiday: bool = False) -> Rule | None:
        """Return the highest-priority rule matching the day, or None."""
        for rule in sorted(person.rules, key=lambda r: (r.priority, r.name)):
            if rule.action == RULE_ACTION_WAKE and rule.wake_time is None:
                continue
            if rule_matches(rule, day, is_holiday):
                return rule
        return None

    def _first_saturday_rule(self, person: PersonConfig) -> Rule | None:
        """Find the highest-priority enabled wake rule that includes Saturday."""
        for rule in sorted(person.rules, key=lambda r: (r.priority, r.name)):
            if not rule.enabled or rule.action != RULE_ACTION_WAKE or rule.wake_time is None:
                continue
            if rule.weekdays and 5 in rule.weekdays:
                return rule
        return None

    def _build(
        self, person: PersonConfig, day: date, wake_time: time, tzinfo,
        state: WakeState, decided_by: str, reason: str, *,
        holiday_name: str | None = None, skip_active: bool = False,
        override_until: date | None = None, matched_rule_id: str | None = None,
    ) -> WakeDecision:
        wake_dt = datetime.combine(day, wake_time, tzinfo=tzinfo)
        window = timedelta(minutes=person.wake_window_minutes)
        return WakeDecision(
            wake_time=wake_time, state=state, decided_by=decided_by, reason=reason,
            holiday_name=holiday_name, skip_active=skip_active, override_until=override_until,
            next_wake=wake_dt,
            wake_window_start=wake_dt - window,
            wake_window_end=wake_dt + window,
            matched_rule_id=matched_rule_id,
        )

    def _apply_calendar_conflict(
        self,
        person: PersonConfig,
        day: date,
        now: datetime,
        decision: WakeDecision,
        calendar: CalendarDecision | None,
    ) -> WakeDecision:
        """Warn about or adjust wake time for early timed calendar events."""
        if (
            calendar is None
            or calendar.early_event_time is None
            or decision.wake_time is None
            or person.calendar_conflict_behavior == CONFLICT_IGNORE
        ):
            return decision

        event_dt = datetime.combine(day, calendar.early_event_time, tzinfo=now.tzinfo)
        suggested_dt = event_dt - timedelta(minutes=person.routine_duration_minutes)
        wake_dt = datetime.combine(day, decision.wake_time, tzinfo=now.tzinfo)
        if suggested_dt >= wake_dt:
            return decision

        suggested_time = suggested_dt.time().replace(second=0, microsecond=0)
        if person.calendar_conflict_behavior == CONFLICT_WAKE_EARLIER:
            adjusted = self._build(
                person,
                day,
                suggested_time,
                now.tzinfo,
                WakeState.SCHEDULED,
                "calendar_conflict",
                f"Earlier appointment {calendar.early_event_time.strftime('%H:%M')}: wake {person.routine_duration_minutes} min before",
                matched_rule_id=decision.matched_rule_id,
            )
            adjusted.calendar_conflict_time = calendar.early_event_time
            adjusted.calendar_suggested_wake_time = suggested_time
            adjusted.calendar_conflict_summary = calendar.summary
            return adjusted

        if person.calendar_conflict_behavior == CONFLICT_WARN_ONLY:
            decision.reason = (
                f"{decision.reason} · Appointment {calendar.early_event_time.strftime('%H:%M')} "
                f"would suggest {suggested_time.strftime('%H:%M')}"
            )
            decision.calendar_conflict_time = calendar.early_event_time
            decision.calendar_suggested_wake_time = suggested_time
            decision.calendar_conflict_summary = calendar.summary
        return decision
