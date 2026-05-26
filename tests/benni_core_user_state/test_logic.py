"""Unit-Tests für benni_core_user_state.logic.

Deckt alle Regeln aus LH Context State v1.1 §5 (R-US-01..R-US-07) plus
Edge Cases aus §9 ab. Reine Python-Tests, kein HA nötig.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcus_const as C
import bcus_logic as L


TZ = timezone(timedelta(hours=2))
NOW = datetime(2026, 5, 26, 8, 0, tzinfo=TZ)


def _persisted(
    state: C.BioState,
    sleep_at: datetime | None = None,
    awake_at: datetime | None = None,
) -> "L.UserStatePersisted":
    return L.UserStatePersisted(
        bio_state=state, sleep_started_at=sleep_at, awake_started_at=awake_at
    )


def _inputs(
    pc: bool | None = False,
    ps5: bool | None = False,
    coffee: bool | None = False,
    phase: str | None = "morning",
) -> "L.UserStateInputs":
    return L.UserStateInputs(
        pc_active=pc, ps5_active=ps5, coffee_active=coffee, master_phase=phase
    )


# ─────────────────────────────────────────────────────────────────────────────
# R-US-01 + R-US-02: SLEEP_REQUEST mit PC-Guard
# ─────────────────────────────────────────────────────────────────────────────


def test_sleep_request_from_awake_pc_inactive_enters_sleep():
    # R-US-01
    p = _persisted(C.BioState.AWAKE, awake_at=NOW - timedelta(hours=10))
    r = L.compute_user_state(p, L.TriggerKind.SLEEP_REQUEST, _inputs(pc=False), NOW)
    assert r.bio_state == C.BioState.SLEEP
    assert r.sleep_started_at == NOW
    assert r.trigger_blocked is False
    assert r.state_changed is True


def test_sleep_request_with_pc_active_is_blocked():
    # R-US-02
    p = _persisted(C.BioState.AWAKE, awake_at=NOW - timedelta(hours=1))
    r = L.compute_user_state(p, L.TriggerKind.SLEEP_REQUEST, _inputs(pc=True), NOW)
    assert r.bio_state == C.BioState.AWAKE
    assert r.trigger_blocked is True
    assert "pc_active=True" in r.trigger_blocked_reason
    assert r.state_changed is False


def test_sleep_request_with_pc_unknown_is_blocked_conservatively():
    # LH §2.1: pc_active unknown → konservativ als aktiv
    p = _persisted(C.BioState.AWAKE, awake_at=NOW - timedelta(hours=1))
    r = L.compute_user_state(p, L.TriggerKind.SLEEP_REQUEST, _inputs(pc=None), NOW)
    assert r.bio_state == C.BioState.AWAKE
    assert r.trigger_blocked is True
    assert "unknown" in r.trigger_blocked_reason


def test_sleep_request_when_already_sleeping_is_noop():
    p = _persisted(C.BioState.SLEEP, sleep_at=NOW - timedelta(hours=4))
    r = L.compute_user_state(p, L.TriggerKind.SLEEP_REQUEST, _inputs(pc=False), NOW)
    assert r.bio_state == C.BioState.SLEEP
    assert r.trigger_blocked is False
    assert r.state_changed is False  # sleep_started_at bleibt = unverändert


# ─────────────────────────────────────────────────────────────────────────────
# R-US-03: WAKING_SIGNAL
# ─────────────────────────────────────────────────────────────────────────────


def test_waking_signal_from_sleep_enters_waking():
    p = _persisted(C.BioState.SLEEP, sleep_at=NOW - timedelta(hours=7))
    r = L.compute_user_state(p, L.TriggerKind.WAKING_SIGNAL, _inputs(phase="morning"), NOW)
    assert r.bio_state == C.BioState.WAKING
    assert r.trigger_blocked is False


def test_waking_signal_from_awake_is_blocked():
    # waking nur aus sleep — aus awake ergibt es keinen Sinn
    p = _persisted(C.BioState.AWAKE, awake_at=NOW - timedelta(hours=1))
    r = L.compute_user_state(p, L.TriggerKind.WAKING_SIGNAL, _inputs(phase="morning"), NOW)
    assert r.bio_state == C.BioState.AWAKE
    assert r.trigger_blocked is True
    assert "nicht sleep" in r.trigger_blocked_reason


# ─────────────────────────────────────────────────────────────────────────────
# R-US-04: AWAKE_SIGNAL
# ─────────────────────────────────────────────────────────────────────────────


def test_awake_signal_from_sleep_enters_awake():
    p = _persisted(C.BioState.SLEEP, sleep_at=NOW - timedelta(hours=8))
    r = L.compute_user_state(p, L.TriggerKind.AWAKE_SIGNAL, _inputs(phase="morning"), NOW)
    assert r.bio_state == C.BioState.AWAKE
    assert r.awake_started_at == NOW
    # sleep_started_at bleibt erhalten (letzte Sleep-Periode-Marker)
    assert r.sleep_started_at == NOW - timedelta(hours=8)


def test_awake_signal_from_waking_enters_awake():
    p = _persisted(C.BioState.WAKING, sleep_at=NOW - timedelta(hours=8), awake_at=None)
    r = L.compute_user_state(p, L.TriggerKind.AWAKE_SIGNAL, _inputs(phase="morning"), NOW)
    assert r.bio_state == C.BioState.AWAKE
    assert r.awake_started_at == NOW


def test_awake_signal_when_already_awake_is_noop():
    p = _persisted(C.BioState.AWAKE, awake_at=NOW - timedelta(hours=2))
    r = L.compute_user_state(p, L.TriggerKind.AWAKE_SIGNAL, _inputs(phase="morning"), NOW)
    assert r.bio_state == C.BioState.AWAKE
    assert r.state_changed is False
    assert r.trigger_blocked is False


# ─────────────────────────────────────────────────────────────────────────────
# R-US-06: Wake via Opening / Coffee (master_phase-gated)
# ─────────────────────────────────────────────────────────────────────────────


def test_opening_activity_at_morning_wakes_from_sleep():
    p = _persisted(C.BioState.SLEEP, sleep_at=NOW - timedelta(hours=7))
    r = L.compute_user_state(
        p, L.TriggerKind.OPENING_ACTIVITY, _inputs(phase="morning"), NOW
    )
    assert r.bio_state == C.BioState.AWAKE
    assert r.awake_started_at == NOW
    assert r.trigger_blocked is False


def test_opening_activity_at_night_does_not_wake():
    # R-US-06 master_phase-gate: nachts kein Wake
    p = _persisted(C.BioState.SLEEP, sleep_at=NOW - timedelta(hours=4))
    r = L.compute_user_state(
        p, L.TriggerKind.OPENING_ACTIVITY, _inputs(phase="night"), NOW
    )
    assert r.bio_state == C.BioState.SLEEP
    assert r.trigger_blocked is True
    assert "night" in r.trigger_blocked_reason


def test_coffee_started_at_evening_wakes_from_sleep():
    p = _persisted(C.BioState.SLEEP, sleep_at=NOW - timedelta(hours=1))
    r = L.compute_user_state(
        p, L.TriggerKind.COFFEE_STARTED, _inputs(phase="evening"), NOW
    )
    assert r.bio_state == C.BioState.AWAKE


def test_opening_when_already_awake_is_noop_not_blocked():
    # Semantisch: opening event ist nur relevant wenn man schläft.
    # Wenn man schon awake ist, ist es kein "block", sondern just irrelevant.
    p = _persisted(C.BioState.AWAKE, awake_at=NOW - timedelta(hours=2))
    r = L.compute_user_state(
        p, L.TriggerKind.OPENING_ACTIVITY, _inputs(phase="morning"), NOW
    )
    assert r.bio_state == C.BioState.AWAKE
    assert r.trigger_blocked is False
    assert r.state_changed is False


# ─────────────────────────────────────────────────────────────────────────────
# R-US-07: Wake via PC / PS5 (master_phase-gated)
# ─────────────────────────────────────────────────────────────────────────────


def test_pc_started_at_morning_wakes_from_sleep():
    p = _persisted(C.BioState.SLEEP, sleep_at=NOW - timedelta(hours=7))
    r = L.compute_user_state(
        p, L.TriggerKind.PC_STARTED, _inputs(pc=True, phase="morning"), NOW
    )
    assert r.bio_state == C.BioState.AWAKE


def test_ps5_started_at_evening_wakes_from_sleep():
    p = _persisted(C.BioState.SLEEP, sleep_at=NOW - timedelta(hours=2))
    r = L.compute_user_state(
        p, L.TriggerKind.PS5_STARTED, _inputs(ps5=True, phase="evening"), NOW
    )
    assert r.bio_state == C.BioState.AWAKE


def test_pc_started_at_night_does_not_wake():
    # LH §9: "PC-Wake-Trigger nachts: R-US-07 hat master_phase-Bedingung.
    # Nachts kann PC aktiv sein ohne Wake auszulösen — verhindert ungewollte
    # Weckung wenn PC z.B. nachts einen Update-Prozess läuft."
    p = _persisted(C.BioState.SLEEP, sleep_at=NOW - timedelta(hours=4))
    r = L.compute_user_state(
        p, L.TriggerKind.PC_STARTED, _inputs(pc=True, phase="night"), NOW
    )
    assert r.bio_state == C.BioState.SLEEP
    assert r.trigger_blocked is True


def test_master_phase_unknown_blocks_wake_conservatively():
    p = _persisted(C.BioState.SLEEP, sleep_at=NOW - timedelta(hours=4))
    r = L.compute_user_state(
        p, L.TriggerKind.PC_STARTED, _inputs(pc=True, phase=None), NOW
    )
    assert r.bio_state == C.BioState.SLEEP
    assert r.trigger_blocked is True
    assert "unknown" in r.trigger_blocked_reason


# ─────────────────────────────────────────────────────────────────────────────
# TICK — Duration-Updates ohne State-Wechsel
# ─────────────────────────────────────────────────────────────────────────────


def test_tick_while_sleeping_computes_sleep_duration():
    p = _persisted(C.BioState.SLEEP, sleep_at=NOW - timedelta(hours=8))
    r = L.compute_user_state(p, L.TriggerKind.TICK, _inputs(phase="morning"), NOW)
    assert r.bio_state == C.BioState.SLEEP
    assert r.sleep_duration_minutes == 480
    assert r.awake_duration_minutes is None
    assert r.state_changed is False


def test_tick_while_awake_computes_awake_duration():
    p = _persisted(C.BioState.AWAKE, awake_at=NOW - timedelta(minutes=125))
    r = L.compute_user_state(p, L.TriggerKind.TICK, _inputs(phase="morning"), NOW)
    assert r.bio_state == C.BioState.AWAKE
    assert r.awake_duration_minutes == 125
    assert r.sleep_duration_minutes is None


def test_tick_while_waking_uses_awake_duration_basis():
    # waking nutzt awake_started_at als Basis — LH definiert es als
    # "Aufwachphase", die in awake übergeht.
    p = _persisted(
        C.BioState.WAKING,
        sleep_at=NOW - timedelta(hours=8),
        awake_at=NOW - timedelta(minutes=5),
    )
    r = L.compute_user_state(p, L.TriggerKind.TICK, _inputs(phase="morning"), NOW)
    assert r.bio_state == C.BioState.WAKING
    assert r.awake_duration_minutes == 5
    assert r.sleep_duration_minutes is None


def test_tick_with_no_timestamps_yields_none_durations():
    # Brand-new persisted state — Bio-State da, aber noch keine Timestamps.
    p = _persisted(C.BioState.AWAKE)
    r = L.compute_user_state(p, L.TriggerKind.TICK, _inputs(phase="morning"), NOW)
    assert r.bio_state == C.BioState.AWAKE
    assert r.awake_duration_minutes is None
    assert r.sleep_duration_minutes is None


# ─────────────────────────────────────────────────────────────────────────────
# Persistenz-Semantik (LH R-US-05)
# ─────────────────────────────────────────────────────────────────────────────


def test_blocked_trigger_does_not_mutate_persisted_state():
    # Wenn ein Trigger blockiert ist, dürfen Timestamps NICHT geändert werden.
    original_sleep_at = NOW - timedelta(hours=4)
    p = _persisted(C.BioState.SLEEP, sleep_at=original_sleep_at)
    r = L.compute_user_state(
        p, L.TriggerKind.PC_STARTED, _inputs(pc=True, phase="night"), NOW
    )
    assert r.sleep_started_at == original_sleep_at


def test_state_changed_false_when_nothing_changes():
    p = _persisted(C.BioState.AWAKE, awake_at=NOW - timedelta(hours=1))
    r = L.compute_user_state(p, L.TriggerKind.TICK, _inputs(phase="morning"), NOW)
    assert r.state_changed is False


def test_state_changed_true_on_real_transition():
    p = _persisted(C.BioState.AWAKE, awake_at=NOW - timedelta(hours=10))
    r = L.compute_user_state(p, L.TriggerKind.SLEEP_REQUEST, _inputs(pc=False), NOW)
    assert r.state_changed is True
