"""Cover-Policy-Coordinator.

Hört auf alle konfigurierten Quell-Entities und auf den eigenen Cover.
Rechnet bei jedem Trigger eine neue Decision (policy.decide); fährt das
Cover nur, wenn `apply_enabled` an ist.

State-Change auf dem Cover innerhalb von `recent_apply_guard_seconds` nach
einem eigenen Schreibvorgang wird ignoriert — ansonsten würde unsere eigene
Bewegung als Manual-Override interpretiert.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)

try:  # HA helper module exists on 2023.x+; tests may run without HA installed.
    from homeassistant.helpers.start import async_at_started
except Exception:  # pragma: no cover - exercised only on bare-bones stubs
    async_at_started = None  # type: ignore[assignment]

from ...const import DATA_ENTRIES, DOMAIN
from ...storage import make_store
from . import policy
from .const import (
    CONF_APPLY_ENABLED,
    CONF_BIO_STATE,
    CONF_COVER_ENTITY,
    CONF_DAY_CONTEXT,
    CONF_DAY_STATE,
    CONF_GAMING_SOURCE,
    CONF_HEAT_PROTECT_ACTIVE,
    CONF_LUX,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MEDIA_CONTEXT,
    CONF_PRESENCE_HOUSEHOLD,
    CONF_PRESENCE_PERSONAL,
    CONF_PROFILE,
    CONF_STARTUP_BLOCK_SECONDS,
    CONF_SUN,
    CONF_WEATHER,
    CONF_WINDOW_STATE,
    DEFAULT_APPLY_ENABLED,
    DEFAULT_GLARE_LUX_THRESHOLD,
    DEFAULT_MANUAL_OVERRIDE_DURATION,
    DEFAULT_PROFILE,
    DEFAULT_RECENT_APPLY_GUARD_SECONDS,
    DEFAULT_STARTUP_BLOCK_SECONDS,
    MODULE_ID,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def _bool_state(s: str | None) -> bool | None:
    if s is None or s in ("unknown", "unavailable"):
        return None
    return s.lower() in ("on", "true", "1", "open", "home", "active", "playing")


def _float_or_none(s: str | None) -> float | None:
    if s in (None, "", "unknown", "unavailable"):
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


class CoverPolicyCoordinator:
    """One coordinator per cover_policy config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store = make_store(
            hass, MODULE_ID, f"state_{entry.entry_id}", version=STORAGE_VERSION
        )
        self._unsub: list[CALLBACK_TYPE] = []
        self._listeners: list = []

        self._started_at: float = time.monotonic()
        self._ha_started: bool = False

        self._last_apply_ts: float = 0.0
        self._manual_override_until: float | None = None
        self._last_decision: policy.Decision | None = None

        # Cancel-handle for the one-shot startup-block expiry timer; lets us
        # cancel during async_stop so a reload doesn't leak callbacks.
        self._startup_unsub: CALLBACK_TYPE | None = None

    # ----- options helpers -----
    @property
    def _data_options(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def _opt(self, key: str, default: Any = None) -> Any:
        return self._data_options.get(key, default)

    @property
    def cover_entity(self) -> str | None:
        return self._opt(CONF_COVER_ENTITY)

    @property
    def apply_enabled(self) -> bool:
        return bool(self._opt(CONF_APPLY_ENABLED, DEFAULT_APPLY_ENABLED))

    @property
    def manual_override_duration(self) -> int:
        return int(self._opt(CONF_MANUAL_OVERRIDE_DURATION, DEFAULT_MANUAL_OVERRIDE_DURATION))

    @property
    def startup_block_seconds(self) -> int:
        return int(self._opt(CONF_STARTUP_BLOCK_SECONDS, DEFAULT_STARTUP_BLOCK_SECONDS))

    @property
    def profile(self) -> dict[str, int]:
        cfg = self._opt(CONF_PROFILE) or {}
        merged = {**DEFAULT_PROFILE, **cfg}
        return merged

    def manual_override_active(self) -> bool:
        return (
            self._manual_override_until is not None
            and time.monotonic() < self._manual_override_until
        )

    def _startup_ready(self) -> bool:
        if not self._ha_started:
            return False
        return (time.monotonic() - self._started_at) >= self.startup_block_seconds

    # ----- listeners -----
    @callback
    def async_start(self) -> None:
        # Robust startup detection: `async_at_started` fires the callback
        # immediately if HA is already running, otherwise once the
        # EVENT_HOMEASSISTANT_STARTED event fires. Using `bus.async_listen_once`
        # alone has a race where the event may have fired before we attach,
        # leaving `_ha_started=False` forever — that is what caused
        # `startup_block` to stick after >> startup_block_seconds.
        if async_at_started is not None:
            self._unsub.append(async_at_started(self.hass, self._on_started))
        elif self.hass.is_running:
            self._on_started(None)
        else:
            self._unsub.append(
                self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, self._on_started)
            )

        watch: set[str] = set()
        for key in (
            CONF_WINDOW_STATE, CONF_BIO_STATE, CONF_PRESENCE_HOUSEHOLD,
            CONF_PRESENCE_PERSONAL, CONF_DAY_STATE, CONF_DAY_CONTEXT,
            CONF_LUX, CONF_SUN, CONF_WEATHER,
            CONF_MEDIA_CONTEXT, CONF_GAMING_SOURCE, CONF_HEAT_PROTECT_ACTIVE,
        ):
            v = self._opt(key)
            if isinstance(v, str) and v:
                watch.add(v)
        if self.cover_entity:
            watch.add(self.cover_entity)

        if watch:
            self._unsub.append(
                async_track_state_change_event(
                    self.hass, list(watch), self._on_state_change
                )
            )

        # Periodic re-evaluate so day_state etc. progress.
        self._unsub.append(
            async_track_time_interval(
                self.hass, self._on_interval, timedelta(seconds=30)
            )
        )

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        if self._startup_unsub is not None:
            self._startup_unsub()
            self._startup_unsub = None

    @callback
    def _on_started(self, _event) -> None:
        self._ha_started = True
        self._started_at = time.monotonic()
        self._schedule_startup_block_expiry()
        self.hass.async_create_task(self.async_evaluate())

    def _schedule_startup_block_expiry(self) -> None:
        """Guarantee a re-evaluation exactly when the startup block lifts.

        Without this, if no source state changes after the startup window,
        `binary_sensor.*_apply_blocked` keeps reporting `startup_block` until
        the next 30-second interval tick — and in some HA setups even longer.
        One-shot timer; cancelled on reload via `async_stop`.
        """
        if self._startup_unsub is not None:
            self._startup_unsub()
            self._startup_unsub = None
        seconds = max(0, int(self.startup_block_seconds))

        @callback
        def _fire(_now) -> None:
            self._startup_unsub = None
            self.hass.async_create_task(self.async_evaluate())

        # +1s safety margin so `_startup_ready()` definitely returns True.
        self._startup_unsub = async_call_later(self.hass, seconds + 1, _fire)

    @callback
    def _on_interval(self, _now) -> None:
        self.hass.async_create_task(self.async_evaluate())

    @callback
    def _on_state_change(self, event: Event) -> None:
        eid = event.data.get("entity_id")
        # Manual-override detection: if the cover state changes outside our
        # recent-apply window, treat as manual interaction.
        if eid == self.cover_entity:
            now = time.monotonic()
            if (now - self._last_apply_ts) > DEFAULT_RECENT_APPLY_GUARD_SECONDS:
                # User moved the cover by hand or via another integration.
                if self.manual_override_duration > 0:
                    self._manual_override_until = now + self.manual_override_duration
        self.hass.async_create_task(self.async_evaluate())

    # ----- persistence -----
    async def async_load(self) -> None:
        raw = await self._store.async_load() or {}
        # Restore manual_override (monotonic-relative) only if still inside
        # the configured duration; otherwise drop.
        remaining = raw.get("manual_override_remaining")
        if isinstance(remaining, (int, float)) and remaining > 0:
            self._manual_override_until = time.monotonic() + float(remaining)

    async def _async_save(self) -> None:
        remaining = None
        if self._manual_override_until is not None:
            remaining = max(0.0, self._manual_override_until - time.monotonic())
        await self._store.async_save({
            "manual_override_remaining": remaining,
            "last_decision": self._last_decision.as_dict() if self._last_decision else None,
            "last_apply_ts_wall": time.time() if self._last_apply_ts else 0,
        })

    # ----- context -----
    def _read_state(self, key: str) -> str | None:
        eid = self._opt(key)
        if not eid:
            return None
        st = self.hass.states.get(eid)
        if st is None or st.state in ("unknown", "unavailable"):
            return None
        return st.state

    def build_context(self) -> policy.Context:
        return policy.Context(
            window_open=_bool_state(self._read_state(CONF_WINDOW_STATE)),
            heat_protect_active=_bool_state(self._read_state(CONF_HEAT_PROTECT_ACTIVE)),
            bio_state=self._read_state(CONF_BIO_STATE),
            day_state=self._read_state(CONF_DAY_STATE),
            day_context=self._read_state(CONF_DAY_CONTEXT),
            presence_household=self._read_state(CONF_PRESENCE_HOUSEHOLD),
            presence_personal=self._read_state(CONF_PRESENCE_PERSONAL),
            lux=_float_or_none(self._read_state(CONF_LUX)),
            sun_above_horizon=(self._read_state(CONF_SUN) == "above_horizon"),
            weather=self._read_state(CONF_WEATHER),
            media_context=self._read_state(CONF_MEDIA_CONTEXT),
            gaming_source=self._read_state(CONF_GAMING_SOURCE),
        )

    # ----- evaluation -----
    async def async_evaluate(self) -> policy.Decision:
        ctx = self.build_context()
        require_window = bool(self._opt(CONF_WINDOW_STATE))
        decision = policy.decide(
            ctx,
            self.profile,
            startup_ready=self._startup_ready(),
            apply_enabled=self.apply_enabled,
            manual_override_active=self.manual_override_active(),
            require_window=require_window,
            glare_lux_threshold=DEFAULT_GLARE_LUX_THRESHOLD,
        )

        # window_open absolute override may clear manual override.
        if decision.manual_override_cleared:
            self._manual_override_until = None

        self._last_decision = decision

        if decision.apply_allowed and decision.target_position is not None and self.cover_entity:
            await self._apply(decision.target_position)

        await self._async_save()
        for cb in self._listeners:
            cb()
        return decision

    async def _apply(self, target: int) -> None:
        target = max(0, min(100, int(target)))
        self._last_apply_ts = time.monotonic()
        try:
            await self.hass.services.async_call(
                "cover",
                "set_cover_position",
                {"entity_id": self.cover_entity, "position": target},
                blocking=False,
            )
        except Exception as err:  # noqa: BLE001 - never let a single call kill the loop
            _LOGGER.warning("cover_policy: set_cover_position failed: %s", err)

    # ----- service surface -----
    async def async_apply_now(self) -> policy.Decision:
        # Bypass the apply_enabled gate? Spec says "explicit safe dry decision"
        # — we honour apply_enabled but always run evaluate().
        return await self.async_evaluate()

    async def async_set_manual_override(self, duration: int | None = None) -> None:
        seconds = int(duration) if duration is not None else self.manual_override_duration
        if seconds <= 0:
            return
        self._manual_override_until = time.monotonic() + seconds
        await self.async_evaluate()

    async def async_clear_manual_override(self) -> None:
        self._manual_override_until = None
        await self.async_evaluate()

    async def async_set_position_profile(self, profile: dict[str, int]) -> None:
        cleaned = {k: max(0, min(100, int(v))) for k, v in (profile or {}).items()
                   if k in DEFAULT_PROFILE}
        new_options = {**self.entry.options, CONF_PROFILE: {**self.profile, **cleaned}}
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)
        await self.async_evaluate()

    # ----- accessors -----
    @property
    def last_decision(self) -> policy.Decision | None:
        return self._last_decision

    def add_listener(self, cb) -> None:
        self._listeners.append(cb)

    def remove_listener(self, cb) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)


# ------------------------------------------------------------------- lookups


def coordinator_from_hass(hass: HomeAssistant, entry_id: str) -> CoverPolicyCoordinator | None:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry_id)
    return bucket.get("coordinator") if bucket else None


def all_cover_policy_coordinators(hass: HomeAssistant) -> list[CoverPolicyCoordinator]:
    out: list[CoverPolicyCoordinator] = []
    for bucket in hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).values():
        if bucket.get("module_id") != MODULE_ID:
            continue
        c = bucket.get("coordinator")
        if c is not None:
            out.append(c)
    return out
