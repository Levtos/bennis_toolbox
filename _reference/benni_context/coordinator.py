"""Central coordinator for Benni Context.

The coordinator owns the computed state of every sensor. Computation is split
into pure helper functions (see ``logic.py``) so it can be tested independently
of Home Assistant. The coordinator's job is to:

* gather raw input from configured Home Assistant entities,
* feed them through the pure logic functions,
* persist what must survive a restart (bio state, preheat),
* push the result to the platform entities.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import logic
from .models import ComputedState, PersistentState
from .const import (
    BIO_SLEEP,
    CONF_COFFEE_ACTIVE,
    CONF_DOOR_WAKE,
    CONF_GPS_PRIMARY,
    CONF_GPS_SECONDARY,
    CONF_HOLIDAY_SENSOR,
    CONF_HOME_RADIUS,
    CONF_HOMEOFFICE_PING,
    CONF_HOUSEHOLD_SOURCE,
    CONF_HYSTERESIS_M,
    CONF_MEDIA_CONTEXT,
    CONF_NEAR_RADIUS,
    CONF_PC_ACTIVE,
    CONF_PREHEAT_DURATION,
    CONF_PREHEAT_RADIUS,
    CONF_PRIVATE_SOURCE,
    CONF_PROXIMITY_DIRECTION,
    CONF_PROXIMITY_DISTANCE,
    CONF_PS5_ACTIVE,
    CONF_TRACKER_FRESHNESS,
    CONF_TRANSITION_HOLD,
    CONF_WAKE_NEEDED,
    CONF_WAKE_NEXT,
    CONF_WLAN_BENNI,
    CONF_WLAN_ELTERN_1,
    CONF_WLAN_ELTERN_2,
    DEFAULT_HOME_RADIUS,
    DEFAULT_HYSTERESIS_M,
    DEFAULT_NEAR_RADIUS,
    DEFAULT_PREHEAT_DURATION,
    DEFAULT_PREHEAT_RADIUS,
    DEFAULT_TRACKER_FRESHNESS,
    DEFAULT_TRANSITION_HOLD,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class BenniContextCoordinator(DataUpdateCoordinator[ComputedState]):
    """Drive all Benni Context sensors from a single computation step."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._persistent = PersistentState()
        self._unsub_listeners: list[CALLBACK_TYPE] = []
        # last presence_personal observed, used to detect coming_home from
        # genuine abwesend (not bei_eltern).
        self._last_real_presence: str | None = None

    # ------------------------------------------------------------------ config

    def _opt(self, key: str, default: Any) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def home_radius(self) -> float:
        return float(self._opt(CONF_HOME_RADIUS, DEFAULT_HOME_RADIUS))

    @property
    def preheat_radius(self) -> float:
        return float(self._opt(CONF_PREHEAT_RADIUS, DEFAULT_PREHEAT_RADIUS))

    @property
    def near_radius(self) -> float:
        return float(self._opt(CONF_NEAR_RADIUS, DEFAULT_NEAR_RADIUS))

    @property
    def hysteresis_m(self) -> float:
        return float(self._opt(CONF_HYSTERESIS_M, DEFAULT_HYSTERESIS_M))

    @property
    def preheat_duration(self) -> int:
        return int(self._opt(CONF_PREHEAT_DURATION, DEFAULT_PREHEAT_DURATION))

    @property
    def tracker_freshness(self) -> int:
        return int(self._opt(CONF_TRACKER_FRESHNESS, DEFAULT_TRACKER_FRESHNESS))

    @property
    def transition_hold(self) -> int:
        return int(self._opt(CONF_TRANSITION_HOLD, DEFAULT_TRANSITION_HOLD))

    def _watched_entity_ids(self) -> list[str]:
        keys = [
            CONF_GPS_PRIMARY,
            CONF_GPS_SECONDARY,
            CONF_WLAN_BENNI,
            CONF_WLAN_ELTERN_1,
            CONF_WLAN_ELTERN_2,
            CONF_PROXIMITY_DISTANCE,
            CONF_PROXIMITY_DIRECTION,
            CONF_WAKE_NEXT,
            CONF_WAKE_NEEDED,
            CONF_PC_ACTIVE,
            CONF_PS5_ACTIVE,
            CONF_COFFEE_ACTIVE,
            CONF_DOOR_WAKE,
            CONF_MEDIA_CONTEXT,
            CONF_PRIVATE_SOURCE,
            CONF_HOMEOFFICE_PING,
            CONF_HOLIDAY_SENSOR,
            CONF_HOUSEHOLD_SOURCE,
        ]
        ids = []
        for k in keys:
            v = self._opt(k, None)
            if isinstance(v, str) and v:
                ids.append(v)
        return ids

    # ------------------------------------------------------------------ storage

    async def async_load_stored(self) -> None:
        raw = await self._store.async_load()
        self._persistent = PersistentState.from_dict(raw)

    async def _async_save(self) -> None:
        await self._store.async_save(self._persistent.to_dict())

    # ------------------------------------------------------------------ listeners

    @callback
    def async_start_listeners(self) -> None:
        ids = self._watched_entity_ids()
        if ids:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass, ids, self._handle_state_change
                )
            )

    @callback
    def async_stop_listeners(self) -> None:
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    @callback
    def _handle_state_change(self, event: Event) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    # ------------------------------------------------------------------ read

    def _read_entity(self, key: str) -> tuple[str | None, datetime | None, dict[str, Any]]:
        eid = self._opt(key, None)
        if not eid:
            return None, None, {}
        state = self.hass.states.get(eid)
        if state is None:
            return None, None, {}
        return state.state, state.last_updated, dict(state.attributes)

    def _read_float(self, key: str) -> float | None:
        val, _, _ = self._read_entity(key)
        if val in (None, "unknown", "unavailable", ""):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _read_bool(self, key: str) -> bool:
        val, _, _ = self._read_entity(key)
        if val is None:
            return False
        return str(val).lower() in ("on", "true", "home", "1", "yes", "active")

    # ------------------------------------------------------------------ compute

    async def _async_update_data(self) -> ComputedState:
        now = dt_util.utcnow()

        # --- raw inputs ----------------------------------------------------
        gps_primary, gps_primary_ts, gps_primary_attrs = self._read_entity(
            CONF_GPS_PRIMARY
        )
        gps_secondary, gps_secondary_ts, _ = self._read_entity(CONF_GPS_SECONDARY)
        wlan_benni, wlan_benni_ts, _ = self._read_entity(CONF_WLAN_BENNI)
        wlan_e1, _, _ = self._read_entity(CONF_WLAN_ELTERN_1)
        wlan_e2, _, _ = self._read_entity(CONF_WLAN_ELTERN_2)
        prox_dist = self._read_float(CONF_PROXIMITY_DISTANCE)
        prox_dir, _, _ = self._read_entity(CONF_PROXIMITY_DIRECTION)

        # --- presence_personal --------------------------------------------
        presence_personal = logic.compute_presence_personal(
            wlan_benni=wlan_benni,
            wlan_benni_ts=wlan_benni_ts,
            wlan_eltern_1=wlan_e1,
            wlan_eltern_2=wlan_e2,
            gps_primary=gps_primary,
            gps_primary_ts=gps_primary_ts,
            gps_secondary=gps_secondary,
            gps_secondary_ts=gps_secondary_ts,
            now=now,
            freshness_s=self.tracker_freshness,
        )

        # household — currently driven solely by personal state, but a
        # configured "household_source" boolean can force nicht_leer (guests,
        # cleaner, etc.).
        external_occupied = self._read_bool(CONF_HOUSEHOLD_SOURCE)
        presence_household = logic.compute_presence_household(
            presence_personal, external_occupied
        )

        # --- presence_band -------------------------------------------------
        prev_band = (
            self.data.presence_band if self.data is not None else None
        )
        presence_band = logic.compute_presence_band(
            distance_m=prox_dist,
            presence_personal=presence_personal,
            home_r=self.home_radius,
            preheat_r=self.preheat_radius,
            near_r=self.near_radius,
            hysteresis_m=self.hysteresis_m,
            prev_band=prev_band,
        )

        # --- transition ----------------------------------------------------
        # We only treat a personal state of "abwesend" as a candidate for
        # coming_home / leaving_home. "bei_eltern" is home-equivalent and
        # never triggers coming_home, even if proximity drops.
        new_trans, trans_started = logic.compute_transition(
            prev_band=prev_band,
            new_band=presence_band,
            prev_personal=self._last_real_presence,
            new_personal=presence_personal,
            direction=prox_dir,
            prev_transition=self._persistent.transition_state,
            prev_started=_parse_iso(self._persistent.transition_started),
            now=now,
            hold_s=self.transition_hold,
        )
        self._persistent.transition_state = new_trans
        self._persistent.transition_started = (
            trans_started.isoformat() if trans_started else None
        )

        # --- preheat -------------------------------------------------------
        preheat_active, preheat_source, preheat_started = logic.compute_preheat(
            band=presence_band,
            direction=prox_dir,
            presence_personal=presence_personal,
            prev_active=self._persistent.preheat_active,
            prev_started=_parse_iso(self._persistent.preheat_started),
            now=now,
            max_duration_s=self.preheat_duration,
        )
        self._persistent.preheat_active = preheat_active
        self._persistent.preheat_source = preheat_source
        self._persistent.preheat_started = (
            preheat_started.isoformat() if preheat_started else None
        )

        # --- bio_state -----------------------------------------------------
        wake_needed = self._read_bool(CONF_WAKE_NEEDED)
        wake_next_raw, _, wake_next_attrs = self._read_entity(CONF_WAKE_NEXT)
        wake_indicators = {
            "pc": self._read_bool(CONF_PC_ACTIVE),
            "ps5": self._read_bool(CONF_PS5_ACTIVE),
            "coffee": self._read_bool(CONF_COFFEE_ACTIVE),
            "door": self._read_bool(CONF_DOOR_WAKE),
            "homeoffice": self._read_bool(CONF_HOMEOFFICE_PING),
        }
        new_bio, sleep_start, awake_start = logic.compute_bio_state(
            prev_state=self._persistent.bio_state,
            wake_needed=wake_needed,
            indicators=wake_indicators,
            presence_personal=presence_personal,
            now=now,
            prev_sleep_start=_parse_iso(self._persistent.last_sleep_start),
            prev_awake_start=_parse_iso(self._persistent.last_awake_start),
        )
        self._persistent.bio_state = new_bio
        self._persistent.last_sleep_start = (
            sleep_start.isoformat() if sleep_start else None
        )
        self._persistent.last_awake_start = (
            awake_start.isoformat() if awake_start else None
        )

        # --- day_state / day_context --------------------------------------
        local_now = dt_util.as_local(now)
        day_state = logic.compute_day_state(local_now)
        holiday = self._read_bool(CONF_HOLIDAY_SENSOR)
        day_context = logic.compute_day_context(local_now, holiday)

        # --- activity -----------------------------------------------------
        media_ctx, _, _ = self._read_entity(CONF_MEDIA_CONTEXT)
        private_active = self._read_bool(CONF_PRIVATE_SOURCE)
        homeoffice = self._read_bool(CONF_HOMEOFFICE_PING)
        activity = logic.compute_activity(
            bio=new_bio,
            presence_personal=presence_personal,
            day_context=day_context,
            day_state=day_state,
            homeoffice=homeoffice,
            private_active=private_active,
            household_active=external_occupied,
            media_context=media_ctx,
        )

        master = ".".join(
            [presence_personal, new_bio, day_state, day_context, activity]
        )

        # --- bookkeeping --------------------------------------------------
        # Track "last real (non-bei_eltern) presence" so coming_home detection
        # only fires after genuine abwesend.
        if presence_personal != "bei_eltern":
            self._last_real_presence = presence_personal

        await self._async_save()

        attrs = {
            "presence_personal": {
                "wlan_benni": wlan_benni,
                "wlan_eltern_1": wlan_e1,
                "wlan_eltern_2": wlan_e2,
                "gps_primary": gps_primary,
                "gps_secondary": gps_secondary,
                "freshness_s": self.tracker_freshness,
            },
            "presence_band": {
                "distance_m": prox_dist,
                "home_radius": self.home_radius,
                "preheat_radius": self.preheat_radius,
                "near_radius": self.near_radius,
                "hysteresis_m": self.hysteresis_m,
            },
            "presence_transition": {
                "started": self._persistent.transition_started,
                "direction": prox_dir,
            },
            "preheat": {
                "source": preheat_source,
                "started": self._persistent.preheat_started,
                "max_duration_s": self.preheat_duration,
            },
            "bio_state": {
                "last_sleep_start": self._persistent.last_sleep_start,
                "last_awake_start": self._persistent.last_awake_start,
                "wake_needed": wake_needed,
                "wake_next": wake_next_raw,
                **{f"indicator_{k}": v for k, v in wake_indicators.items()},
            },
            "activity_state": {
                "media_context": media_ctx,
                "homeoffice": homeoffice,
                "private": private_active,
                "household": external_occupied,
            },
            "master_context": {
                "presence": presence_personal,
                "bio": new_bio,
                "day_state": day_state,
                "day_context": day_context,
                "activity": activity,
            },
        }

        return ComputedState(
            presence_personal=presence_personal,
            presence_household=presence_household,
            presence_band=presence_band,
            presence_transition=new_trans,
            preheat_active=preheat_active,
            preheat_source=preheat_source,
            preheat_started=self._persistent.preheat_started,
            bio_state=new_bio,
            last_sleep_start=self._persistent.last_sleep_start,
            last_awake_start=self._persistent.last_awake_start,
            day_state=day_state,
            day_context=day_context,
            activity_state=activity,
            master_context=master,
            attrs=attrs,
        )


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return dt_util.parse_datetime(raw)
    except Exception:  # noqa: BLE001
        return None
