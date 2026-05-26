"""Reine State-Machine-Logik für User State (Lastenheft Context State v1.1).

Keine HA-Imports — vollständig in pytest testbar.

Verteilung der Verantwortung:
- `logic.py` (hier): pure State-Machine — (persisted, trigger, inputs, now) → result.
- `coordinator.py`: HA-Integration, Storage, Event-Listener, Trigger-Detection.
- `sensor.py`: Mapping auf SensorEntity ohne weitere Logik.

State-Machine-Regeln (LH R-US-01..R-US-07):
- SLEEP_REQUEST → sleep, blockiert wenn pc_active (R-US-01, R-US-02)
- WAKING_SIGNAL → waking, nur aus sleep (R-US-03)
- AWAKE_SIGNAL → awake, aus sleep oder waking (R-US-04)
- OPENING_ACTIVITY / COFFEE / PC / PS5 → awake aus sleep,
  master_phase-gated auf {morning,midday,evening} (R-US-06, R-US-07)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .const import WAKE_TRIGGER_ALLOWED_MASTER_PHASES, BioState


# ─────────────────────────────────────────────────────────────────────────────
# TRIGGER-TYPEN
# ─────────────────────────────────────────────────────────────────────────────


class TriggerKind(str, Enum):
    """Welcher Wake-/Sleep-Trigger hat gefeuert?

    TICK = nur Recompute, kein State-Wechsel — minütlich für Duration-Updates.
    """

    TICK = "tick"
    SLEEP_REQUEST = "sleep_request"
    WAKING_SIGNAL = "waking_signal"
    AWAKE_SIGNAL = "awake_signal"
    OPENING_ACTIVITY = "opening_activity"
    COFFEE_STARTED = "coffee_started"
    PC_STARTED = "pc_started"
    PS5_STARTED = "ps5_started"


# Welche Trigger sind master_phase-gated (LH R-US-06, R-US-07)?
_PHASE_GATED_TRIGGERS: frozenset[TriggerKind] = frozenset(
    {
        TriggerKind.OPENING_ACTIVITY,
        TriggerKind.COFFEE_STARTED,
        TriggerKind.PC_STARTED,
        TriggerKind.PS5_STARTED,
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# DATEN-STRUKTUREN
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserStateInputs:
    """Snapshot der relevanten Eingaben zum Auswertungszeitpunkt.

    Werte können None sein wenn die Source-Entity unavailable ist — siehe
    LH §2.1 Failure-Verhalten.
    """

    pc_active: bool | None
    ps5_active: bool | None
    coffee_active: bool | None
    master_phase: str | None  # aus Day State


@dataclass(frozen=True)
class UserStatePersisted:
    """Persistenter Zustand aus Storage."""

    bio_state: BioState
    sleep_started_at: datetime | None
    awake_started_at: datetime | None


@dataclass(frozen=True)
class UserStateResult:
    """Vollständiges Ergebnis einer User-State-Auswertung."""

    bio_state: BioState
    sleep_started_at: datetime | None
    awake_started_at: datetime | None
    sleep_duration_minutes: int | None
    awake_duration_minutes: int | None
    state_changed: bool
    trigger: TriggerKind
    trigger_blocked: bool
    trigger_blocked_reason: str | None


# ─────────────────────────────────────────────────────────────────────────────
# REINE BAUSTEINE
# ─────────────────────────────────────────────────────────────────────────────


def _can_enter_sleep(inputs: UserStateInputs) -> tuple[bool, str | None]:
    """R-US-02 PC-Guard.

    LH §2.1: Bei pc_active unknown → konservativ als aktiv behandeln.
    Also blockiert sowohl bei True als auch None.
    """
    if inputs.pc_active is False:
        return True, None
    reason = (
        "pc_active=True"
        if inputs.pc_active is True
        else "pc_active=unknown (konservativ als aktiv)"
    )
    return False, reason


def _wake_trigger_phase_ok(inputs: UserStateInputs) -> tuple[bool, str | None]:
    """R-US-06, R-US-07 master_phase-Gate.

    Wake-Trigger greifen nur in master_phase ∈ {morning, midday, evening}.
    Nachts (night) bleibt sleep stabil. Bei master_phase unknown:
    konservativ block (= kein Wake), passend zu LH-Failure-Verhalten.
    """
    if inputs.master_phase is None:
        return False, "master_phase=unknown (konservativ block)"
    if inputs.master_phase in WAKE_TRIGGER_ALLOWED_MASTER_PHASES:
        return True, None
    return False, f"master_phase={inputs.master_phase} (kein Tag-Fenster)"


def _compute_durations(
    bio_state: BioState,
    sleep_started_at: datetime | None,
    awake_started_at: datetime | None,
    now: datetime,
) -> tuple[int | None, int | None]:
    """Berechne aktuelle Sleep-/Awake-Dauer in Minuten.

    Nur die zum aktuellen Bio-State passende Dauer ist gesetzt; die andere
    bleibt None. So sieht der Konsument sofort welche Dauer "läuft".
    """
    sleep_minutes: int | None = None
    awake_minutes: int | None = None
    if bio_state is BioState.SLEEP and sleep_started_at is not None:
        sleep_minutes = max(0, int((now - sleep_started_at).total_seconds() // 60))
    elif (
        bio_state in (BioState.AWAKE, BioState.WAKING)
        and awake_started_at is not None
    ):
        awake_minutes = max(0, int((now - awake_started_at).total_seconds() // 60))
    return sleep_minutes, awake_minutes


def _result(
    *,
    new_state: BioState,
    sleep_started_at: datetime | None,
    awake_started_at: datetime | None,
    persisted: UserStatePersisted,
    trigger: TriggerKind,
    now: datetime,
    blocked: bool = False,
    reason: str | None = None,
) -> UserStateResult:
    """Hilfsfunktion: baut UserStateResult mit Duration-Berechnung +
    state_changed-Detection."""
    sleep_min, awake_min = _compute_durations(
        new_state, sleep_started_at, awake_started_at, now
    )
    changed = (
        new_state is not persisted.bio_state
        or sleep_started_at != persisted.sleep_started_at
        or awake_started_at != persisted.awake_started_at
    )
    return UserStateResult(
        bio_state=new_state,
        sleep_started_at=sleep_started_at,
        awake_started_at=awake_started_at,
        sleep_duration_minutes=sleep_min,
        awake_duration_minutes=awake_min,
        state_changed=changed,
        trigger=trigger,
        trigger_blocked=blocked,
        trigger_blocked_reason=reason,
    )


# ─────────────────────────────────────────────────────────────────────────────
# HAUPTFUNKTION
# ─────────────────────────────────────────────────────────────────────────────


def compute_user_state(
    persisted: UserStatePersisted,
    trigger: TriggerKind,
    inputs: UserStateInputs,
    now: datetime,
) -> UserStateResult:
    """Wendet einen Trigger (oder TICK) auf den persistierten Zustand an.

    Args:
        persisted: Aktueller Zustand aus Storage.
        trigger: Was hat zur Auswertung geführt? TICK = nur Duration-Update.
        inputs: Snapshot der Eingaben zum Auswertungszeitpunkt.
        now: Aktueller Zeitpunkt (TZ-aware).

    Returns:
        UserStateResult — neuer Zustand + abgeleitete Dauern + Tracing.
    """
    current = persisted.bio_state

    # TICK — nur Recompute, kein State-Wechsel
    if trigger is TriggerKind.TICK:
        return _result(
            new_state=current,
            sleep_started_at=persisted.sleep_started_at,
            awake_started_at=persisted.awake_started_at,
            persisted=persisted,
            trigger=trigger,
            now=now,
        )

    # SLEEP_REQUEST — R-US-01 + R-US-02
    if trigger is TriggerKind.SLEEP_REQUEST:
        if current is BioState.SLEEP:
            # Bereits sleep — kein Block. Bootstrap-Repair: wenn der
            # Timestamp fehlt (z.B. nach erstem Setup ohne vorherigen
            # echten Wechsel), jetzt nachsetzen.
            return _result(
                new_state=current,
                sleep_started_at=persisted.sleep_started_at or now,
                awake_started_at=persisted.awake_started_at,
                persisted=persisted,
                trigger=trigger,
                now=now,
            )
        allowed, block_reason = _can_enter_sleep(inputs)
        if not allowed:
            return _result(
                new_state=current,
                sleep_started_at=persisted.sleep_started_at,
                awake_started_at=persisted.awake_started_at,
                persisted=persisted,
                trigger=trigger,
                now=now,
                blocked=True,
                reason=block_reason,
            )
        return _result(
            new_state=BioState.SLEEP,
            sleep_started_at=now,
            awake_started_at=persisted.awake_started_at,
            persisted=persisted,
            trigger=trigger,
            now=now,
        )

    # WAKING_SIGNAL — R-US-03 (nur aus sleep)
    if trigger is TriggerKind.WAKING_SIGNAL:
        if current is not BioState.SLEEP:
            return _result(
                new_state=current,
                sleep_started_at=persisted.sleep_started_at,
                awake_started_at=persisted.awake_started_at,
                persisted=persisted,
                trigger=trigger,
                now=now,
                blocked=True,
                reason=f"current={current.value} (nicht sleep)",
            )
        return _result(
            new_state=BioState.WAKING,
            sleep_started_at=persisted.sleep_started_at,
            awake_started_at=persisted.awake_started_at,
            persisted=persisted,
            trigger=trigger,
            now=now,
        )

    # AWAKE_SIGNAL — R-US-04 (aus sleep oder waking)
    if trigger is TriggerKind.AWAKE_SIGNAL:
        if current is BioState.AWAKE:
            # Bereits awake — kein State-Wechsel. Bootstrap-Repair: wenn
            # der Timestamp fehlt (z.B. nach erstem Setup ohne vorherigen
            # echten Wechsel), jetzt nachsetzen. Dann tickern auch die
            # Duration-Sensoren korrekt los.
            return _result(
                new_state=current,
                sleep_started_at=persisted.sleep_started_at,
                awake_started_at=persisted.awake_started_at or now,
                persisted=persisted,
                trigger=trigger,
                now=now,
            )
        return _result(
            new_state=BioState.AWAKE,
            sleep_started_at=persisted.sleep_started_at,
            awake_started_at=now,
            persisted=persisted,
            trigger=trigger,
            now=now,
        )

    # Wake-Trigger über Aktivitäts-Signale — R-US-06, R-US-07
    if trigger in _PHASE_GATED_TRIGGERS:
        if current is not BioState.SLEEP:
            # Nur aus sleep heraus relevant. Kein "Block" weil semantisch
            # einfach unnötig (man ist schon wach).
            return _result(
                new_state=current,
                sleep_started_at=persisted.sleep_started_at,
                awake_started_at=persisted.awake_started_at,
                persisted=persisted,
                trigger=trigger,
                now=now,
            )
        phase_ok, phase_reason = _wake_trigger_phase_ok(inputs)
        if not phase_ok:
            return _result(
                new_state=current,
                sleep_started_at=persisted.sleep_started_at,
                awake_started_at=persisted.awake_started_at,
                persisted=persisted,
                trigger=trigger,
                now=now,
                blocked=True,
                reason=phase_reason,
            )
        return _result(
            new_state=BioState.AWAKE,
            sleep_started_at=persisted.sleep_started_at,
            awake_started_at=now,
            persisted=persisted,
            trigger=trigger,
            now=now,
        )

    # Sollte nie erreicht werden — alle TriggerKind-Werte sind abgedeckt.
    raise ValueError(f"Unhandled trigger: {trigger}")
