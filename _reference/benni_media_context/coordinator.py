"""DataUpdateCoordinator for benni_media_context."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN, DEFAULT_DEBOUNCE, DEFAULT_QUIET_DUCK,
    DEFAULT_BASE_VOL_HOMEPODS, DEFAULT_BASE_VOL_DENON,
    DEFAULT_BOOST_OFFSET, DEFAULT_WINDOW_OFFSET,
    DEFAULT_APPLETV_APP_MAP,
    CONF_TV_ACTIVE, CONF_TV_SOURCE, CONF_TV_POWER_FALLBACK, CONF_APPLETV,
    CONF_PS5_STATUS, CONF_PS5_TITLE, CONF_SWITCH_DOCK, CONF_PC_ACTIVE,
    CONF_DENON_ACTIVE, CONF_HOMEPODS, CONF_TITLE_CLASSIFIER_PS5, CONF_TITLE_CLASSIFIER_PC,
    CONF_TITLE_CLASSIFIER_HOMEPODS, CONF_TITLE_CLASSIFIER_MEDIA, CONF_DOOR, CONF_CALL_MONITOR,
    CONF_DAY_STATE, CONF_ACTIVITY_STATE, CONF_WINDOW_STATE,
    CONF_APPLETV_APP_MAP,
    CONF_DEBOUNCE, CONF_QUIET_DUCK, CONF_BASE_VOL_HOMEPODS, CONF_BASE_VOL_DENON,
    CONF_BOOST_OFFSET, CONF_WINDOW_OFFSET,
    CTX_IDLE,
)
from .logic import Snapshot, Decision, decide

_LOGGER = logging.getLogger(__name__)


def _bool_state(v: Optional[str]) -> bool:
    if v is None:
        return False
    return str(v).lower() in ("on", "true", "1", "active", "open", "playing", "home", "detected")


def _maybe_int(v: Optional[str], default: int = 0) -> int:
    if v is None or v in ("unknown", "unavailable", "none", ""):
        return default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


class BenniMediaCoordinator(DataUpdateCoordinator[Decision]):
    """Coordinator. Event-driven; recomputes whenever a tracked entity changes."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # event driven
        )
        self.entry = entry
        self._unsub_state = None

        # Session-persistent state
        self._pre_atv_scenario: Optional[Decision] = None
        self._last_stable: Decision = Decision()
        self._pending_decision: Optional[Decision] = None
        self._pending_since: float = 0.0
        self._manual_nudge: Optional[str] = None

        self.data = Decision()

    # -- options helpers --
    def _opt(self, key: str, default: Any) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    def _entity(self, key: str) -> Optional[str]:
        v = self.entry.data.get(key)
        return v or None

    def _entities_list(self, key: str) -> list[str]:
        v = self.entry.data.get(key)
        if not v:
            return []
        if isinstance(v, list):
            return v
        return [v]

    def _app_map(self) -> dict[str, str]:
        return self.entry.data.get(CONF_APPLETV_APP_MAP, DEFAULT_APPLETV_APP_MAP)

    # -- lifecycle --
    async def async_setup(self) -> None:
        entities: list[str] = []
        for key in (
            CONF_TV_ACTIVE, CONF_TV_SOURCE, CONF_TV_POWER_FALLBACK, CONF_APPLETV,
            CONF_PS5_STATUS, CONF_PS5_TITLE, CONF_SWITCH_DOCK, CONF_PC_ACTIVE,
            CONF_DENON_ACTIVE, CONF_TITLE_CLASSIFIER_PS5, CONF_TITLE_CLASSIFIER_PC, CONF_TITLE_CLASSIFIER_HOMEPODS,
            CONF_TITLE_CLASSIFIER_MEDIA, CONF_DOOR, CONF_CALL_MONITOR, CONF_DAY_STATE,
            CONF_ACTIVITY_STATE, CONF_WINDOW_STATE,
        ):
            e = self._entity(key)
            if e:
                entities.append(e)
        for e in self._entities_list(CONF_HOMEPODS):
            entities.append(e)

        if entities:
            self._unsub_state = async_track_state_change_event(
                self.hass, entities, self._handle_state_event
            )
        await self.async_recalculate()

    async def async_unload(self) -> None:
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None

    # -- state change handler --
    @callback
    def _handle_state_event(self, event: Event) -> None:
        self.hass.async_create_task(self.async_recalculate())

    # -- snapshot construction --
    def _build_snapshot(self) -> Snapshot:
        hass = self.hass
        s = Snapshot()

        def _state(key: str) -> Optional[str]:
            ent = self._entity(key)
            if not ent:
                return None
            st = hass.states.get(ent)
            if st is None or st.state in ("unavailable", "unknown"):
                return None
            return st.state

        def _attr(key: str, attr: str) -> Optional[str]:
            ent = self._entity(key)
            if not ent:
                return None
            st = hass.states.get(ent)
            if st is None:
                return None
            return st.attributes.get(attr)

        s.tv_active = _bool_state(_state(CONF_TV_ACTIVE))
        s.tv_source = _state(CONF_TV_SOURCE)
        tv_power_raw = _state(CONF_TV_POWER_FALLBACK)
        s.tv_power = _bool_state(tv_power_raw) if tv_power_raw is not None else None

        s.atv_state = _state(CONF_APPLETV)
        s.atv_app_id = _attr(CONF_APPLETV, "app_id") or _attr(CONF_APPLETV, "app_name")
        s.atv_title = _attr(CONF_APPLETV, "media_title")

        s.ps5_status = _state(CONF_PS5_STATUS)
        s.ps5_title = _state(CONF_PS5_TITLE)
        if s.ps5_status in ("on", "playing") and not s.ps5_title:
            s.ps5_title = ""  # explicit empty = menu/default

        s.switch_dock = _bool_state(_state(CONF_SWITCH_DOCK))
        s.pc_active = _bool_state(_state(CONF_PC_ACTIVE))
        s.denon_active = _bool_state(_state(CONF_DENON_ACTIVE))

        hp_playing = False
        for ent in self._entities_list(CONF_HOMEPODS):
            st = hass.states.get(ent)
            if st and st.state == "playing":
                hp_playing = True
                break
        s.homepods_playing = hp_playing

        s.classifier_ps5 = _maybe_int(_state(CONF_TITLE_CLASSIFIER_PS5))
        s.classifier_pc = _maybe_int(_state(CONF_TITLE_CLASSIFIER_PC))
        s.classifier_homepods = _maybe_int(_state(CONF_TITLE_CLASSIFIER_HOMEPODS))
        s.classifier_media = _maybe_int(_state(CONF_TITLE_CLASSIFIER_MEDIA))

        s.door_open = _bool_state(_state(CONF_DOOR))
        s.call_active = _bool_state(_state(CONF_CALL_MONITOR))
        s.day_state = _state(CONF_DAY_STATE)
        s.activity_state = _state(CONF_ACTIVITY_STATE)
        s.window_open = _bool_state(_state(CONF_WINDOW_STATE))

        s.manual_nudge = self._manual_nudge
        return s

    # -- recalculate --
    async def async_recalculate(self) -> None:
        snap = self._build_snapshot()
        new = decide(
            snap,
            app_map=self._app_map(),
            base_homepods=float(self._opt(CONF_BASE_VOL_HOMEPODS, DEFAULT_BASE_VOL_HOMEPODS)),
            base_denon=float(self._opt(CONF_BASE_VOL_DENON, DEFAULT_BASE_VOL_DENON)),
            boost_offset=float(self._opt(CONF_BOOST_OFFSET, DEFAULT_BOOST_OFFSET)),
            window_offset=float(self._opt(CONF_WINDOW_OFFSET, DEFAULT_WINDOW_OFFSET)),
            quiet_duck=float(self._opt(CONF_QUIET_DUCK, DEFAULT_QUIET_DUCK)),
            pre_atv_scenario=self._pre_atv_scenario,
        )
        debounce = float(self._opt(CONF_DEBOUNCE, DEFAULT_DEBOUNCE))
        now = time.monotonic()

        # Quiet bypasses debounce
        if new.quiet_mode_active or self.data.quiet_mode_active:
            self._commit(new, snap)
            return

        # Same context as last stable -> commit immediately (refresh attrs)
        if new.context == self._last_stable.context and new.subcontext == self._last_stable.subcontext:
            self._pending_decision = None
            self._commit(new, snap)
            return

        # Different context -> debounce
        if self._pending_decision is None or (
            new.context != self._pending_decision.context
            or new.subcontext != self._pending_decision.subcontext
        ):
            self._pending_decision = new
            self._pending_since = now
            # publish current (stable) but with updated attrs
            interim = Decision(**{**self._last_stable.to_dict()})
            interim.volume_target_homepods = new.volume_target_homepods
            interim.volume_target_denon = new.volume_target_denon
            interim.subwoofer_allowed = new.subwoofer_allowed
            interim.active_reasons = self._last_stable.active_reasons + [
                f"debouncing->{new.context}/{new.subcontext}"
            ]
            self.async_set_updated_data(interim)
            self.hass.loop.call_later(debounce + 0.1, lambda: self.hass.async_create_task(self.async_recalculate()))
            return

        if now - self._pending_since >= debounce:
            self._commit(new, snap)
        else:
            # still debouncing
            interim = Decision(**{**self._last_stable.to_dict()})
            interim.active_reasons = self._last_stable.active_reasons + [
                f"debouncing->{new.context}/{new.subcontext}"
            ]
            self.async_set_updated_data(interim)

    def _commit(self, new: Decision, snap: Snapshot) -> None:
        # Track pre-ATV scenario: snapshot last stable non-streaming-ATV state
        from .const import CTX_STREAMING
        if self._last_stable.context not in (CTX_STREAMING,) and new.context == CTX_STREAMING:
            # entering streaming -> remember what we had before
            self._pre_atv_scenario = self._last_stable

        self._last_stable = new
        self._pending_decision = None
        self.async_set_updated_data(new)

    # -- service hooks --
    def set_manual_nudge(self, value: str) -> None:
        self._manual_nudge = value
        self.hass.async_create_task(self.async_recalculate())

    def clear_manual_nudge(self) -> None:
        self._manual_nudge = None
        self.hass.async_create_task(self.async_recalculate())
