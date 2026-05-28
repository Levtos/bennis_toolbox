"""Reine Compute-Logik für Benni Core · Devices (LH device_core v0.2).

Keine HA-Imports — vollständig in pytest testbar.

Verteilung:
- `logic.py` (hier): pure Funktionen — (config, inputs, persisted, now) → result
- `coordinator.py`: HA-Integration, Storage, Event-Listener
- `sensor.py`/`binary_sensor.py`: Mapping auf Entities

Regeln R-DC-01..R-DC-09 aus dem Lastenheft.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .const import (
    AVAILABILITY_FRESHNESS_SECONDS,
    BOOT_INITIAL_PHASE_SECONDS,
    DEFAULT_STICKY_HOLD_SECONDS,
    DEFAULT_WATT_THRESHOLD_ON,
    PowerSource,
    PowerState,
)


# ─────────────────────────────────────────────────────────────────────────────
# DATEN-STRUKTUREN
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SlotReading:
    """Snapshot eines Slots zum Auswertungszeitpunkt.

    `value` ist der raw-State als String, oder None wenn unavailable/unknown.
    `numeric` ist der konvertierte Float (für Watt-Sensoren), sonst None.
    `last_updated` markiert wann der Slot zuletzt frische Daten lieferte.
    """

    value: str | None
    numeric: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    last_updated: datetime | None = None


@dataclass(frozen=True)
class DeviceConfig:
    """Konfiguration eines Devices (aus Config Flow)."""

    slug: str
    display_name: str
    device_type: str
    watt_threshold_on: int = DEFAULT_WATT_THRESHOLD_ON
    watt_buckets: tuple["WattBucket", ...] = ()
    sticky_hold_seconds: int = DEFAULT_STICKY_HOLD_SECONDS
    area_id: str | None = None
    # Slot-Schlüssel die der User konfiguriert hat (für Reading-Lookup)
    configured_slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class WattBucket:
    """Bucket-Eintrag für `power_state`-Ableitung (R-DC-06).

    state: semantischer State (off/idle/playing/...).
    op:    Vergleichsoperator gegen den Watt-Wert (<, <=, =, >, >=).
           None = catch-all (matcht immer).
    value: Vergleichswert in Watt. None = catch-all.

    Auswertung: Buckets werden in Reihenfolge geprüft, erster Treffer gewinnt.
    Die Reihenfolge bestimmt der User (off → idle → playing).
    """

    state: str
    op: str | None = None
    value: float | None = None


# Erlaubte Vergleichsoperatoren für Watt-Buckets.
WATT_OPERATORS: tuple[str, ...] = ("<", "<=", "=", ">", ">=")


def _match_operator(op: str, watt: float, value: float) -> bool:
    if op == "<":
        return watt < value
    if op == "<=":
        return watt <= value
    if op == "=":
        return watt == value
    if op == ">":
        return watt > value
    if op == ">=":
        return watt >= value
    return False


@dataclass(frozen=True)
class Override:
    """Aktiver Override-Eintrag (R-DC-07)."""

    powered: bool | None
    power_state: str | None
    expires_at: datetime | None


@dataclass(frozen=True)
class DevicePersisted:
    """Persistenter Zustand pro Device (für Sticky-Hold + Override)."""

    last_powered: bool | None
    last_powered_change: datetime | None
    override: Override | None


@dataclass(frozen=True)
class DeviceInputs:
    """Snapshot aller Slot-Readings + Boot-Phase-Indikator."""

    slots: dict[str, SlotReading]
    integration_slot: str | None
    state_slot: str | None
    watt_slot: str | None  # Falls vorhanden, der numerische Watt-Sensor
    boot_phase_active: bool


@dataclass(frozen=True)
class DeviceResult:
    """Vollständiges Auswertungsergebnis (was ans Sensor-Layer geht)."""

    state: str  # semantischer Haupt-State (typabhängig)
    powered: bool | None
    power_state: str  # PowerState-Slug
    power_source: str  # PowerSource-Slug
    available: bool
    last_powered_change: datetime | None
    override_active: bool
    watt_disagrees: bool
    watt: float | None
    raw_state: str | None  # raw value des state_slots
    extra: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# HILFSFUNKTIONEN
# ─────────────────────────────────────────────────────────────────────────────


_TRUTHY = frozenset(
    {
        "on", "home", "true", "1", "yes", "active", "playing", "open",
        # climate hvac_mode-Werte (Thermostat aktiv = powered)
        "heat", "cool", "auto", "heat_cool", "dry", "fan_only",
    }
)
_FALSY = frozenset({"off", "not_home", "false", "0", "no", "inactive", "idle", "closed"})


def _as_bool(value: str | None) -> bool | None:
    """Konvertiere raw-State zu bool; None bei unbekannt."""
    if value is None:
        return None
    v = value.strip().lower()
    if v in _TRUTHY:
        return True
    if v in _FALSY:
        return False
    return None


def _is_fresh(reading: SlotReading | None, now: datetime, max_age: int) -> bool:
    """Slot frisch? Hat einen Wert UND ist nicht zu alt."""
    if reading is None or reading.value is None:
        return False
    if reading.last_updated is None:
        # Kein Timestamp → wir trauen dem Wert (HA liefert immer einen).
        return True
    return (now - reading.last_updated).total_seconds() <= max_age


def classify_power_state(
    watt: float | None, buckets: tuple[WattBucket, ...]
) -> str:
    """R-DC-06: Watt → semantischer power_state.

    Ohne buckets oder watt → "unknown".
    Mit buckets: in Reihenfolge prüfen, erster Treffer gewinnt. Ein Bucket
    ohne Operator/Value gilt als catch-all (matcht immer).
    """
    if not buckets or watt is None:
        return PowerState.UNKNOWN.value
    for b in buckets:
        if b.op is None or b.value is None:
            return b.state  # catch-all
        if _match_operator(b.op, watt, b.value):
            return b.state
    return PowerState.UNKNOWN.value


# ─────────────────────────────────────────────────────────────────────────────
# HAUPTFUNKTION
# ─────────────────────────────────────────────────────────────────────────────


def compute_device(
    config: DeviceConfig,
    inputs: DeviceInputs,
    persisted: DevicePersisted,
    now: datetime,
) -> DeviceResult:
    """Wertet alle Regeln R-DC-01..R-DC-09 aus.

    Reihenfolge:
    1. Override aktiv (R-DC-07) → direkt setzen
    2. Integration first (R-DC-01.1)
    3. Watt-Fallback (R-DC-01.2)
    4. Sticky-Hold (R-DC-01.3), aber nicht in Boot-Phase (R-DC-09)
    5. Sonst: powered=None, power_source="none"

    Zusätzlich immer:
    - power_state aus Watt-Buckets (R-DC-06), unabhängig von 1-4
    - available (R-DC-03)
    - watt_disagrees (R-DC-05)
    """
    integration_reading = inputs.slots.get(inputs.integration_slot) if inputs.integration_slot else None
    state_reading = inputs.slots.get(inputs.state_slot) if inputs.state_slot else None
    watt_reading = inputs.slots.get(inputs.watt_slot) if inputs.watt_slot else None

    watt = watt_reading.numeric if watt_reading is not None else None
    integration_fresh = _is_fresh(integration_reading, now, AVAILABILITY_FRESHNESS_SECONDS)
    integration_bool = _as_bool(integration_reading.value) if integration_reading else None
    watt_fresh = watt_reading is not None and watt is not None

    # ── power_state: immer aus Watt (R-DC-06)
    power_state = classify_power_state(watt, config.watt_buckets)

    # ── Override (R-DC-07)
    override = persisted.override
    override_active = (
        override is not None
        and (override.expires_at is None or now < override.expires_at)
    )
    if override_active:
        assert override is not None  # for type checkers
        return DeviceResult(
            state=_compute_state(state_reading, override.powered, inputs.state_slot),
            powered=override.powered,
            power_state=override.power_state or power_state,
            power_source=PowerSource.OVERRIDE.value,
            available=_compute_available(inputs, now),
            last_powered_change=persisted.last_powered_change,
            override_active=True,
            watt_disagrees=False,
            watt=watt,
            raw_state=state_reading.value if state_reading else None,
            extra=state_reading.attributes if state_reading else {},
        )

    # ── R-DC-01: Fallback-Hierarchie für `powered`
    powered: bool | None = None
    source = PowerSource.NONE
    if integration_fresh and integration_bool is not None:
        powered = integration_bool
        source = PowerSource.INTEGRATION
    elif watt_fresh:
        powered = bool(watt is not None and watt >= config.watt_threshold_on)
        source = PowerSource.WATT_FALLBACK
    elif not inputs.boot_phase_active:
        # Sticky-Hold (R-DC-02), nur außerhalb Boot-Phase (R-DC-09)
        age = _sticky_age_seconds(persisted, now)
        if (
            persisted.last_powered is not None
            and age is not None
            and age <= config.sticky_hold_seconds
        ):
            powered = persisted.last_powered
            source = PowerSource.STICKY_HOLD

    # ── R-DC-05: Konflikt Integration vs. Watt
    watt_disagrees = False
    if source is PowerSource.INTEGRATION and watt_fresh and watt is not None:
        # Integration sagt off, aber Watt über Threshold? → flagge
        if powered is False and watt >= config.watt_threshold_on:
            watt_disagrees = True

    # ── last_powered_change ableiten
    new_last_change = persisted.last_powered_change
    if powered != persisted.last_powered:
        new_last_change = now

    return DeviceResult(
        state=_compute_state(state_reading, powered, inputs.state_slot),
        powered=powered,
        power_state=power_state,
        power_source=source.value,
        available=_compute_available(inputs, now),
        last_powered_change=new_last_change,
        override_active=False,
        watt_disagrees=watt_disagrees,
        watt=watt,
        raw_state=state_reading.value if state_reading else None,
        extra=state_reading.attributes if state_reading else {},
    )


# ─────────────────────────────────────────────────────────────────────────────
# AUX
# ─────────────────────────────────────────────────────────────────────────────


def _compute_state(
    state_reading: SlotReading | None,
    powered: bool | None,
    state_slot: str | None,
) -> str:
    """R-DC-04: State-Mapping.

    - Stateful (state_slot gesetzt + Reading vorhanden): nimm raw value
      des state_slots (z.B. media_player playing/paused/idle/off).
    - Sonst aus powered ableiten: on/off/unavailable.
    """
    if state_slot and state_reading is not None and state_reading.value is not None:
        return state_reading.value
    if powered is True:
        return "on"
    if powered is False:
        return "off"
    return "unavailable"


def _compute_available(inputs: DeviceInputs, now: datetime) -> bool:
    """R-DC-03: available = mindestens ein konfigurierter Slot ist frisch."""
    return any(
        _is_fresh(r, now, AVAILABILITY_FRESHNESS_SECONDS)
        for r in inputs.slots.values()
    )


def _sticky_age_seconds(persisted: DevicePersisted, now: datetime) -> float | None:
    if persisted.last_powered_change is None:
        return None
    return (now - persisted.last_powered_change).total_seconds()


def is_boot_phase(boot_start: datetime, now: datetime) -> bool:
    """R-DC-09: Erste BOOT_INITIAL_PHASE_SECONDS nach Modul-Setup."""
    return (now - boot_start) < timedelta(seconds=BOOT_INITIAL_PHASE_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
# WATT-BUCKETS Parsing (aus Config Flow / Storage)
# ─────────────────────────────────────────────────────────────────────────────


def parse_watt_buckets(raw: Any) -> tuple[WattBucket, ...]:
    """Parst eine Bucket-Liste aus Config-Flow / Storage / Import.

    Erwartetes Format (Reihenfolge = Auswertungsreihenfolge):
        [{"state": "off", "op": "<=", "value": 5},
         {"state": "idle", "op": "<=", "value": 30},
         {"state": "playing", "op": ">", "value": 30}]

    Ein Eintrag ohne op/value gilt als catch-all. Reihenfolge bleibt erhalten
    (kein Re-Sort — der User bestimmt die Priorität).

    Robust gegen None/leere/kaputte Werte: ungültige Einträge werden
    übersprungen.
    """
    if not raw or not isinstance(raw, list):
        return ()
    out: list[WattBucket] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        state = entry.get("state")
        if not isinstance(state, str) or not state:
            continue
        op = entry.get("op")
        value_raw = entry.get("value")
        # catch-all: weder op noch value
        if op in (None, "") and value_raw in (None, ""):
            out.append(WattBucket(state=state, op=None, value=None))
            continue
        if op not in WATT_OPERATORS:
            continue
        try:
            value = float(value_raw)
        except (TypeError, ValueError):
            continue
        out.append(WattBucket(state=state, op=op, value=value))
    return tuple(out)


# ─────────────────────────────────────────────────────────────────────────────
# Override-Lifecycle
# ─────────────────────────────────────────────────────────────────────────────


def build_override(
    powered: bool | None,
    power_state: str | None,
    expire_seconds: int | None,
    now: datetime,
) -> Override:
    """Baue Override-Objekt aus Service-Parametern."""
    expires_at = now + timedelta(seconds=expire_seconds) if expire_seconds else None
    return Override(
        powered=powered,
        power_state=power_state,
        expires_at=expires_at,
    )


def is_override_expired(override: Override | None, now: datetime) -> bool:
    if override is None:
        return True
    if override.expires_at is None:
        return False
    return now >= override.expires_at
