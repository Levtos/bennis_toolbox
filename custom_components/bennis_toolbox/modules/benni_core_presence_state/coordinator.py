"""DataUpdateCoordinator für Benni Core · Presence State.

Verantwortung:
- Storage-backed persistenter Zustand (home_candidate, home_gate, band,
  preheat, transition) — überlebt HA-Restarts.
- State-Change-Listener auf alle Tracker-/Proximity-Entities + minütliches
  Polling für Timer-Ablauf-Checks.
- Komposition aller Outputs über logic.compute_* + lokale Timer-Logik.

Timer-Strategie: poll-basiert über persistierte Timestamps statt asyncio.
Bei jedem Refresh wird ausgewertet, ob Delays/Hold-Zeiten abgelaufen sind.
Robuster gegen HA-Restarts als event-basierte Timer.

R-PS-08 (Preheat-Auslösung über Quellzonen-Exit) ist als TODO markiert —
braucht zusätzlichen Person-State-Change-Listener und Zone-Tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from ...const import DOMAIN
from ...storage import make_store
from . import logic
from .const import (
    CONF_HOME_RADIUS_M,
    CONF_HYSTERESIS_M,
    CONF_ICLOUD_TRACKER,
    CONF_MOBILE_TRACKER,
    CONF_NEAR_RADIUS_M,
    CONF_PERSON,
    CONF_PREHEAT_DURATION_S,
    CONF_PREHEAT_RADIUS_M,
    CONF_PROXIMITY_DIRECTION,
    CONF_PROXIMITY_DISTANCE,
    CONF_SOURCE_ZONES,
    CONF_WLAN_BENNI_TRACKER,
    CONF_WLAN_ELTERN_TRACKERS,
    DEFAULT_HOME_RADIUS_M,
    DEFAULT_HYSTERESIS_M,
    DEFAULT_NEAR_RADIUS_M,
    DEFAULT_PREHEAT_DURATION_S,
    DEFAULT_PREHEAT_RADIUS_M,
    HOME_GATE_ENTRY_DELAY_S,
    HOME_GATE_EXIT_DELAY_S,
    MODULE_ID,
    STORAGE_VERSION,
    TRANSITION_HOLD_S,
    UPDATE_INTERVAL_SECONDS,
    Band,
    Direction,
    PresenceHousehold,
    PresencePersonal,
    Transition,
)
from .logic import PresenceInputs, TrackerSnapshot

_LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DATEN-STRUKTUREN
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _Persisted:
    """Persistenter Zustand — alle Felder JSON-serialisierbar."""

    home_candidate: bool = False
    home_candidate_changed_at: datetime | None = None
    home_gate: bool = False
    last_band: Band | None = None
    transition_kind: Transition = Transition.NONE
    transition_started_at: datetime | None = None
    preheat_active: bool = False
    preheat_source: str | None = None
    preheat_started_at: datetime | None = None


@dataclass(frozen=True)
class PresenceComputed:
    """Output-Snapshot, von Sensoren konsumiert."""

    personal: PresencePersonal
    household: PresenceHousehold
    transition: Transition
    band: Band
    direction: Direction
    distance_m: float | None
    preheat_active: bool
    preheat_source: str | None
    # Tracing-Felder
    home_candidate: bool
    home_candidate_reason: str
    home_gate: bool
    bei_eltern: bool


# ─────────────────────────────────────────────────────────────────────────────
# COORDINATOR
# ─────────────────────────────────────────────────────────────────────────────


class PresenceStateCoordinator(DataUpdateCoordinator[PresenceComputed]):
    """Treibt alle Presence-Sensoren."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{MODULE_ID}_{entry.entry_id}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.entry = entry
        self._store = make_store(
            hass, MODULE_ID, f"state_{entry.entry_id}", version=STORAGE_VERSION
        )
        self._state = _Persisted()
        self._unsub_listeners: list[CALLBACK_TYPE] = []

    # ─────────────────────────────────────────────────────── Config Access

    def _opt(self, key: str, default: Any = None) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def home_radius_m(self) -> int:
        return int(self._opt(CONF_HOME_RADIUS_M, DEFAULT_HOME_RADIUS_M))

    @property
    def near_radius_m(self) -> int:
        return int(self._opt(CONF_NEAR_RADIUS_M, DEFAULT_NEAR_RADIUS_M))

    @property
    def preheat_radius_m(self) -> int:
        return int(self._opt(CONF_PREHEAT_RADIUS_M, DEFAULT_PREHEAT_RADIUS_M))

    @property
    def hysteresis_m(self) -> int:
        return int(self._opt(CONF_HYSTERESIS_M, DEFAULT_HYSTERESIS_M))

    @property
    def preheat_duration_s(self) -> int:
        return int(self._opt(CONF_PREHEAT_DURATION_S, DEFAULT_PREHEAT_DURATION_S))

    def _watched_entities(self) -> list[str]:
        ids: list[str] = []
        for key in (
            CONF_ICLOUD_TRACKER,
            CONF_MOBILE_TRACKER,
            CONF_WLAN_BENNI_TRACKER,
            CONF_PROXIMITY_DISTANCE,
            CONF_PROXIMITY_DIRECTION,
            CONF_PERSON,
        ):
            v = self._opt(key)
            if isinstance(v, str) and v:
                ids.append(v)
        eltern = self._opt(CONF_WLAN_ELTERN_TRACKERS, []) or []
        if isinstance(eltern, list):
            ids.extend(e for e in eltern if isinstance(e, str) and e)
        return ids

    # ─────────────────────────────────────────────────────── Storage

    async def async_load_stored(self) -> None:
        raw = await self._store.async_load()
        if raw is None:
            await self._async_save()
            return
        self._state = _persisted_from_dict(raw)

    async def _async_save(self) -> None:
        await self._store.async_save(_persisted_to_dict(self._state))

    # ─────────────────────────────────────────────────────── Lifecycle

    def async_start_listeners(self) -> None:
        ids = self._watched_entities()
        if ids:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass, ids, self._async_on_input_change
                )
            )

    def async_stop_listeners(self) -> None:
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    @callback
    def _async_on_input_change(self, event: Event) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    # ─────────────────────────────────────────────────────── Compute

    async def _async_update_data(self) -> PresenceComputed:
        now = dt_util.now()
        inputs = self._read_inputs()

        # 1. Home-Candidate
        new_candidate, candidate_reason = logic.compute_home_candidate(
            inputs, now, last_candidate=self._state.home_candidate
        )
        if new_candidate != self._state.home_candidate:
            self._state.home_candidate = new_candidate
            self._state.home_candidate_changed_at = now

        # 2. Home-Gate Stabilisierung (R-PS-04)
        self._evaluate_home_gate(now)

        # 3. Band
        new_band = logic.compute_band(
            inputs.distance_m,
            self._state.last_band,
            self.home_radius_m,
            self.near_radius_m,
            self.preheat_radius_m,
            self.hysteresis_m,
        )
        band_changed_to_preheat = (
            new_band is Band.PREHEAT and self._state.last_band is not Band.PREHEAT
        )
        self._state.last_band = new_band

        # 4. bei_eltern + presence_personal
        bei_eltern = logic.is_bei_eltern(new_band, inputs.wlan_benni, now)
        personal = logic.compute_presence_personal(
            home_gate=self._state.home_gate, bei_eltern=bei_eltern
        )

        # 5. Household
        household = logic.compute_household(personal, inputs.wlan_eltern)

        # 6. Preheat-Auslösung Ring (R-PS-07)
        if (
            band_changed_to_preheat
            and inputs.direction == Direction.TOWARDS.value
            and personal is not PresencePersonal.ZUHAUSE
            and not self._state.preheat_active
        ):
            self._start_preheat("ring", now)

        # 7. Preheat-Ende (R-PS-09, R-PS-10, Timeout)
        self._evaluate_preheat_end(now, new_band, inputs.direction)

        # 8. Transition-Hold-Ablauf
        self._evaluate_transition_expiry(now)

        await self._async_save()

        direction_enum = _parse_direction(inputs.direction)
        return PresenceComputed(
            personal=personal,
            household=household,
            transition=self._state.transition_kind,
            band=new_band,
            direction=direction_enum,
            distance_m=inputs.distance_m,
            preheat_active=self._state.preheat_active,
            preheat_source=self._state.preheat_source,
            home_candidate=self._state.home_candidate,
            home_candidate_reason=candidate_reason,
            home_gate=self._state.home_gate,
            bei_eltern=bei_eltern,
        )

    # ─────────────────────────────────────────────────────── Helpers

    def _evaluate_home_gate(self, now: datetime) -> None:
        """R-PS-04: Stabilisierung 60s entry / 150s exit."""
        cand = self._state.home_candidate
        gate = self._state.home_gate
        since = self._state.home_candidate_changed_at
        if cand == gate or since is None:
            return  # nichts zu tun
        elapsed = (now - since).total_seconds()
        if cand and not gate and elapsed >= HOME_GATE_ENTRY_DELAY_S:
            self._state.home_gate = True
            self._set_transition(Transition.COMING_HOME, now)
            # Wenn preheat aktiv: beenden (R-PS-09)
            if self._state.preheat_active:
                self._stop_preheat()
        elif not cand and gate and elapsed >= HOME_GATE_EXIT_DELAY_S:
            self._state.home_gate = False
            self._set_transition(Transition.LEAVING_HOME, now)

    def _evaluate_preheat_end(
        self, now: datetime, band: Band, direction: str | None
    ) -> None:
        if not self._state.preheat_active:
            return
        started = self._state.preheat_started_at
        # R-PS-10: passing_through bei away_from + far
        if direction == Direction.AWAY_FROM.value and band is Band.FAR:
            self._stop_preheat()
            self._set_transition(Transition.PASSING_THROUGH, now)
            return
        # Timeout
        if started and (now - started).total_seconds() >= self.preheat_duration_s:
            self._stop_preheat()

    def _evaluate_transition_expiry(self, now: datetime) -> None:
        if self._state.transition_kind is Transition.NONE:
            return
        started = self._state.transition_started_at
        if started and (now - started).total_seconds() >= TRANSITION_HOLD_S:
            self._state.transition_kind = Transition.NONE
            self._state.transition_started_at = None

    def _set_transition(self, kind: Transition, now: datetime) -> None:
        self._state.transition_kind = kind
        self._state.transition_started_at = now

    def _start_preheat(self, source: str, now: datetime) -> None:
        self._state.preheat_active = True
        self._state.preheat_source = source
        self._state.preheat_started_at = now

    def _stop_preheat(self) -> None:
        self._state.preheat_active = False
        self._state.preheat_source = None
        self._state.preheat_started_at = None

    # ─────────────────────────────────────────────────────── Input-Read

    def _read_inputs(self) -> PresenceInputs:
        return PresenceInputs(
            icloud=self._read_tracker(CONF_ICLOUD_TRACKER),
            mobile=self._read_tracker(CONF_MOBILE_TRACKER),
            wlan_benni=self._read_tracker(CONF_WLAN_BENNI_TRACKER),
            wlan_eltern=tuple(
                self._read_tracker_eid(eid)
                for eid in (self._opt(CONF_WLAN_ELTERN_TRACKERS, []) or [])
                if isinstance(eid, str) and eid
            ),
            distance_m=self._read_float(CONF_PROXIMITY_DISTANCE),
            direction=self._read_raw(CONF_PROXIMITY_DIRECTION),
        )

    def _read_tracker(self, key: str) -> TrackerSnapshot:
        eid = self._opt(key)
        if not eid:
            return TrackerSnapshot(is_home=None, last_updated=None)
        return self._read_tracker_eid(eid)

    def _read_tracker_eid(self, eid: str) -> TrackerSnapshot:
        state = self.hass.states.get(eid)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
            return TrackerSnapshot(is_home=None, last_updated=None)
        s = str(state.state).lower()
        if s in (STATE_HOME, "on", "true", "1", "yes"):
            is_home = True
        elif s in (STATE_NOT_HOME, "off", "false", "0", "no"):
            is_home = False
        else:
            # Person in einer benannten Zone (z.B. "work") gilt als not_home
            # für die "ist Benni in der Heimzone"-Frage
            is_home = False
        return TrackerSnapshot(is_home=is_home, last_updated=state.last_updated)

    def _read_float(self, key: str) -> float | None:
        raw = self._read_raw(key)
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _read_raw(self, key: str) -> str | None:
        eid = self._opt(key)
        if not eid:
            return None
        state = self.hass.states.get(eid)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
            return None
        return state.state


# ─────────────────────────────────────────────────────────────────────────────
# Module-Level Helpers
# ─────────────────────────────────────────────────────────────────────────────


@callback
def coordinator_from_hass(
    hass: HomeAssistant, entry: ConfigEntry
) -> PresenceStateCoordinator | None:
    from ...const import DATA_ENTRIES

    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    if not bucket:
        return None
    return bucket.get("coordinator")


def _parse_direction(raw: str | None) -> Direction:
    if raw is None:
        return Direction.UNKNOWN
    try:
        return Direction(raw.lower())
    except ValueError:
        return Direction.UNKNOWN


def _persisted_to_dict(p: _Persisted) -> dict[str, Any]:
    return {
        "home_candidate": p.home_candidate,
        "home_candidate_changed_at": _iso(p.home_candidate_changed_at),
        "home_gate": p.home_gate,
        "last_band": p.last_band.value if p.last_band else None,
        "transition_kind": p.transition_kind.value,
        "transition_started_at": _iso(p.transition_started_at),
        "preheat_active": p.preheat_active,
        "preheat_source": p.preheat_source,
        "preheat_started_at": _iso(p.preheat_started_at),
    }


def _persisted_from_dict(raw: dict[str, Any]) -> _Persisted:
    last_band_raw = raw.get("last_band")
    last_band = None
    if isinstance(last_band_raw, str):
        try:
            last_band = Band(last_band_raw)
        except ValueError:
            last_band = None

    trans_raw = raw.get("transition_kind", Transition.NONE.value)
    try:
        transition = Transition(trans_raw) if isinstance(trans_raw, str) else Transition.NONE
    except ValueError:
        transition = Transition.NONE

    return _Persisted(
        home_candidate=bool(raw.get("home_candidate", False)),
        home_candidate_changed_at=_parse_iso(raw.get("home_candidate_changed_at")),
        home_gate=bool(raw.get("home_gate", False)),
        last_band=last_band,
        transition_kind=transition,
        transition_started_at=_parse_iso(raw.get("transition_started_at")),
        preheat_active=bool(raw.get("preheat_active", False)),
        preheat_source=raw.get("preheat_source"),
        preheat_started_at=_parse_iso(raw.get("preheat_started_at")),
    )


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse_iso(v: Any) -> datetime | None:
    if not isinstance(v, str) or not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None
