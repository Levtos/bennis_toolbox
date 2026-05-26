"""DataUpdateCoordinator für Benni Core · User State.

Verantwortlich für:
- Storage-backed Bio-State + Sleep/Awake-Timestamps (R-US-05)
- Event-Listener auf alle Wake-Trigger-Entities (PC, PS5, Kaffee, Opening)
- Day-State-Source-Read für master_phase-Gate (R-US-06, R-US-07)
- Minütlicher Tick für Duration-Sensor-Updates
- Service-Handler für manuelle Bio-State-Setter (set_sleep/waking/awake)

Compute-Logik lebt in `logic.py` als pure State-Machine.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from ...const import DOMAIN
from ...storage import make_store
from . import logic
from .const import (
    CONF_COFFEE_ACTIVE,
    CONF_DAY_STATE_SOURCE,
    CONF_OPENING_ENTITIES,
    CONF_PC_ACTIVE,
    CONF_PS5_ACTIVE,
    DEFAULT_BIO_STATE,
    DEFAULT_DAY_STATE_SOURCE,
    MODULE_ID,
    STORAGE_KEY_AWAKE_STARTED_AT,
    STORAGE_KEY_BIO_STATE,
    STORAGE_KEY_SLEEP_STARTED_AT,
    STORAGE_VERSION,
    UPDATE_INTERVAL_SECONDS,
    BioState,
)
from .logic import TriggerKind, UserStateInputs, UserStatePersisted, UserStateResult

_LOGGER = logging.getLogger(__name__)

# Boolean-ähnliche Strings, die als "aktiv" zählen (Wake-Trigger / PC-Guard).
_TRUTHY_STATES = frozenset({"on", "home", "true", "1", "yes", "active", "playing"})
_FALSY_STATES = frozenset({"off", "not_home", "false", "0", "no", "inactive", "idle"})


class UserStateCoordinator(DataUpdateCoordinator[UserStateResult]):
    """Treibt die drei User-State-Sensoren."""

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
        self._persisted: UserStatePersisted = UserStatePersisted(
            bio_state=DEFAULT_BIO_STATE,
            sleep_started_at=None,
            awake_started_at=None,
        )
        self._unsub_listeners: list[CALLBACK_TYPE] = []
        # Letzter bekannter raw-Wert pro Trigger-Entity, damit wir
        # Übergänge off→on erkennen statt jedes Event neu zu feuern.
        self._last_raw_state: dict[str, str | None] = {}

    # ─────────────────────────────────────────────────────── Config Access

    def _opt(self, key: str, default: Any = None) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def day_state_source(self) -> str:
        return self._opt(CONF_DAY_STATE_SOURCE, DEFAULT_DAY_STATE_SOURCE)

    @property
    def pc_active_entity(self) -> str | None:
        return self._opt(CONF_PC_ACTIVE)

    @property
    def ps5_active_entity(self) -> str | None:
        return self._opt(CONF_PS5_ACTIVE)

    @property
    def coffee_active_entity(self) -> str | None:
        return self._opt(CONF_COFFEE_ACTIVE)

    @property
    def opening_entities(self) -> list[str]:
        v = self._opt(CONF_OPENING_ENTITIES, [])
        return list(v) if isinstance(v, list) else []

    def _trigger_entity_for(self, kind: TriggerKind) -> str | None:
        """Welche Entity gehört zu welchem TriggerKind?"""
        return {
            TriggerKind.PC_STARTED: self.pc_active_entity,
            TriggerKind.PS5_STARTED: self.ps5_active_entity,
            TriggerKind.COFFEE_STARTED: self.coffee_active_entity,
        }.get(kind)

    # ─────────────────────────────────────────────────────── Storage

    async def async_load_stored(self) -> None:
        raw = await self._store.async_load()
        if raw is None:
            # Allererster Start nach Config Flow — keine Persistenz vorhanden.
            # Wir initialisieren mit DEFAULT_BIO_STATE und setzen einen
            # passenden Started-At-Timestamp, damit die Duration-Sensoren
            # sofort tickern statt unknown zu bleiben.
            now = dt_util.now()
            self._persisted = UserStatePersisted(
                bio_state=DEFAULT_BIO_STATE,
                sleep_started_at=now if DEFAULT_BIO_STATE is BioState.SLEEP else None,
                awake_started_at=now if DEFAULT_BIO_STATE is BioState.AWAKE else None,
            )
            await self._async_save()
            return
        self._persisted = _persisted_from_dict(raw)

    async def _async_save(self) -> None:
        await self._store.async_save(_persisted_to_dict(self._persisted))

    # ─────────────────────────────────────────────────────── Lifecycle

    def async_start_listeners(self) -> None:
        watched: list[str] = []
        if self.pc_active_entity:
            watched.append(self.pc_active_entity)
        if self.ps5_active_entity:
            watched.append(self.ps5_active_entity)
        if self.coffee_active_entity:
            watched.append(self.coffee_active_entity)
        watched.extend(self.opening_entities)

        # Initial-State des letzten raw-Werts merken, sodass beim allerersten
        # Event nicht fälschlich ein Wake getriggert wird.
        for eid in watched:
            self._last_raw_state[eid] = _read_raw_state(self.hass, eid)

        if watched:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass, watched, self._async_on_trigger_entity_change
                )
            )

    def async_stop_listeners(self) -> None:
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    # ─────────────────────────────────────────────────────── Event-Handler

    @callback
    def _async_on_trigger_entity_change(self, event: Event) -> None:
        """State-Change einer Trigger-Entity → Trigger-Detection + Recompute."""
        eid: str = event.data.get("entity_id", "")
        new_state = event.data.get("new_state")
        new_raw = new_state.state if new_state is not None else None
        old_raw = self._last_raw_state.get(eid)
        self._last_raw_state[eid] = new_raw

        # Welcher Trigger-Typ?
        trigger = self._classify_trigger(eid, old_raw, new_raw)
        if trigger is None:
            return

        self.hass.async_create_task(self._async_apply_trigger(trigger))

    def _classify_trigger(
        self, eid: str, old_raw: str | None, new_raw: str | None
    ) -> TriggerKind | None:
        """Welche TriggerKind entspricht diesem State-Change?

        Logik:
        - PC/PS5/Coffee: nur off→on zählt (PC_STARTED etc.). on→off ignorieren.
        - Opening: jeder Wechsel zählt (LH: "bewegt"), aber Wertewechsel
          unknown↔normal nicht.
        """
        if eid == self.pc_active_entity:
            return TriggerKind.PC_STARTED if _became_truthy(old_raw, new_raw) else None
        if eid == self.ps5_active_entity:
            return TriggerKind.PS5_STARTED if _became_truthy(old_raw, new_raw) else None
        if eid == self.coffee_active_entity:
            return (
                TriggerKind.COFFEE_STARTED if _became_truthy(old_raw, new_raw) else None
            )
        if eid in self.opening_entities and _is_real_transition(old_raw, new_raw):
            return TriggerKind.OPENING_ACTIVITY
        return None

    async def _async_apply_trigger(self, trigger: TriggerKind) -> None:
        result = self._compute(trigger)
        await self._persist_if_changed(result)
        self.async_set_updated_data(result)

    async def async_apply_service_trigger(self, kind: TriggerKind) -> UserStateResult:
        """Manueller Trigger via Service-Aufruf (set_sleep/waking/awake)."""
        result = self._compute(kind)
        await self._persist_if_changed(result)
        self.async_set_updated_data(result)
        return result

    # ─────────────────────────────────────────────────────── Compute

    async def _async_update_data(self) -> UserStateResult:
        # Reine Tick-Berechnung (Duration-Update). State-Wechsel laufen
        # über _async_apply_trigger oder Service-Calls.
        return self._compute(TriggerKind.TICK)

    def _compute(self, trigger: TriggerKind) -> UserStateResult:
        now = dt_util.now()
        inputs = self._read_inputs()
        return logic.compute_user_state(self._persisted, trigger, inputs, now)

    async def _persist_if_changed(self, result: UserStateResult) -> None:
        if not result.state_changed:
            return
        self._persisted = UserStatePersisted(
            bio_state=result.bio_state,
            sleep_started_at=result.sleep_started_at,
            awake_started_at=result.awake_started_at,
        )
        await self._async_save()

    def _read_inputs(self) -> UserStateInputs:
        return UserStateInputs(
            pc_active=_read_bool(self.hass, self.pc_active_entity),
            ps5_active=_read_bool(self.hass, self.ps5_active_entity),
            coffee_active=_read_bool(self.hass, self.coffee_active_entity),
            master_phase=_read_master_phase(self.hass, self.day_state_source),
        )


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — am Modul-Scope, damit Sensor sie auch nutzen kann
# ─────────────────────────────────────────────────────────────────────────────


@callback
def coordinator_from_hass(
    hass: HomeAssistant, entry: ConfigEntry
) -> UserStateCoordinator | None:
    from ...const import DATA_ENTRIES

    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    if not bucket:
        return None
    return bucket.get("coordinator")


def _read_raw_state(hass: HomeAssistant, eid: str | None) -> str | None:
    if not eid:
        return None
    state = hass.states.get(eid)
    return state.state if state is not None else None


def _read_bool(hass: HomeAssistant, eid: str | None) -> bool | None:
    """LH §2.1: bei unknown/unavailable konservativ — None signalisiert das."""
    raw = _read_raw_state(hass, eid)
    if raw is None or raw in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
        return None
    rl = str(raw).lower()
    if rl in _TRUTHY_STATES:
        return True
    if rl in _FALSY_STATES:
        return False
    return None


def _read_master_phase(hass: HomeAssistant, day_state_eid: str) -> str | None:
    state = hass.states.get(day_state_eid)
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    mp = state.attributes.get("master_phase")
    return mp if isinstance(mp, str) and mp else None


def _became_truthy(old_raw: str | None, new_raw: str | None) -> bool:
    """Übergang off→on (oder unbekannt→on)?"""
    new_truthy = new_raw is not None and new_raw.lower() in _TRUTHY_STATES
    old_truthy = old_raw is not None and old_raw.lower() in _TRUTHY_STATES
    return new_truthy and not old_truthy


def _is_real_transition(old_raw: str | None, new_raw: str | None) -> bool:
    """Echter on↔off-Wechsel? Ignoriert Übergänge zu/von unknown/unavailable."""
    if old_raw is None or new_raw is None:
        return False
    if old_raw in (STATE_UNAVAILABLE, STATE_UNKNOWN, "") or new_raw in (
        STATE_UNAVAILABLE,
        STATE_UNKNOWN,
        "",
    ):
        return False
    return old_raw != new_raw


# ─────────────────────────────────────────────────────────────────────────────
# Persistenz-Codec
# ─────────────────────────────────────────────────────────────────────────────


def _persisted_to_dict(p: UserStatePersisted) -> dict[str, Any]:
    return {
        STORAGE_KEY_BIO_STATE: p.bio_state.value,
        STORAGE_KEY_SLEEP_STARTED_AT: (
            p.sleep_started_at.isoformat() if p.sleep_started_at else None
        ),
        STORAGE_KEY_AWAKE_STARTED_AT: (
            p.awake_started_at.isoformat() if p.awake_started_at else None
        ),
    }


def _persisted_from_dict(raw: dict[str, Any]) -> UserStatePersisted:
    bio_raw = raw.get(STORAGE_KEY_BIO_STATE)
    bio = (
        BioState(bio_raw)
        if isinstance(bio_raw, str) and bio_raw in (s.value for s in BioState)
        else DEFAULT_BIO_STATE
    )
    return UserStatePersisted(
        bio_state=bio,
        sleep_started_at=_parse_iso(raw.get(STORAGE_KEY_SLEEP_STARTED_AT)),
        awake_started_at=_parse_iso(raw.get(STORAGE_KEY_AWAKE_STARTED_AT)),
    )


def _parse_iso(v: Any) -> datetime | None:
    if not isinstance(v, str) or not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None
