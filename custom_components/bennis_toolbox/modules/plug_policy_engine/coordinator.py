"""Coordinator für Plug Policy Engine.

Liest HA-State, ruft die reine `engine.evaluate(...)`-Funktion und (optional)
treibt Switches. Cross-Modul-Inputs (Context/Media/Wake/Title-Classifier)
kommen ausschließlich als HA-Entity-IDs aus der Konfig — kein Python-Import
anderer Toolbox-Module.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from ...const import DATA_ENTRIES, DOMAIN
from ...storage import make_store
from .const import (
    CONF_ACTIVE_THRESHOLD,
    CONF_ACTIVITY,
    CONF_ALLOWED_CONTEXTS,
    CONF_BATTERY,
    CONF_BIO,
    CONF_DAY,
    CONF_DEADBAND_HIGH,
    CONF_DEADBAND_LOW,
    CONF_DEVICES,
    CONF_DIFFUSER_OFF_MIN,
    CONF_DIFFUSER_ON_MIN,
    CONF_ENABLE_CONTROL,
    CONF_ENTERTAINMENT,
    CONF_IDLE_THRESHOLD,
    CONF_KIND,
    CONF_MANUAL_COOLDOWN,
    CONF_MEDIA,
    CONF_NAME,
    CONF_NEVER_CUT_ACTIVE,
    CONF_POLICY,
    CONF_POWER,
    CONF_PRESENCE,
    CONF_SCAN_INTERVAL,
    CONF_STABLE_OFF,
    CONF_SWITCH,
    CONF_TABLET_HIGH,
    CONF_TABLET_LOW,
    CONF_UNKNOWN,
    CONF_WAKE_SIGNAL_ONLY,
    DEFAULT_SCAN_INTERVAL,
    DESIRED_KEEP,
    DESIRED_OFF,
    DESIRED_ON,
    MODULE_ID,
    STORAGE_VERSION,
)
from .engine import Decision, DeviceConfig, DeviceState, GlobalContext, evaluate

_LOGGER = logging.getLogger(__name__)


class PlugPolicyCoordinator:
    """Liest HA-State, ruft die reine Engine, exposes Decisions, treibt Switches optional."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store = make_store(
            hass, MODULE_ID, f"state_{entry.entry_id}", version=STORAGE_VERSION
        )
        self._unsub: list = []
        self._listeners: list = []
        self._ha_started = False

        data = {**entry.data, **entry.options}
        self.enable_control: bool = bool(data.get(CONF_ENABLE_CONTROL, False))
        self.scan_interval: int = int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

        self.global_entities = {
            "presence": data.get(CONF_PRESENCE),
            "bio": data.get(CONF_BIO),
            "day": data.get(CONF_DAY),
            "media": data.get(CONF_MEDIA),
            "entertainment": data.get(CONF_ENTERTAINMENT),
            "activity": data.get(CONF_ACTIVITY),
        }

        self.configs: dict[str, DeviceConfig] = {}
        for d in data.get(CONF_DEVICES, []):
            cfg = DeviceConfig(
                device_id=d["device_id"],
                name=d.get(CONF_NAME, d["device_id"]),
                switch_entity=d[CONF_SWITCH],
                power_entity=d.get(CONF_POWER),
                battery_entity=d.get(CONF_BATTERY),
                policy=d.get(CONF_POLICY, "HB"),
                kind=d.get(CONF_KIND, "generic"),
                active_threshold=float(d.get(CONF_ACTIVE_THRESHOLD, 5.0)),
                idle_threshold=float(d.get(CONF_IDLE_THRESHOLD, 2.0)),
                deadband_lower=d.get(CONF_DEADBAND_LOW),
                deadband_upper=d.get(CONF_DEADBAND_HIGH),
                stable_off_seconds=int(d.get(CONF_STABLE_OFF, 600)),
                unknown_behavior=d.get(CONF_UNKNOWN, "assume_active"),
                allowed_contexts=list(d.get(CONF_ALLOWED_CONTEXTS, [])),
                never_cut_when_active=bool(d.get(CONF_NEVER_CUT_ACTIVE, True)),
                wake_signal_only=bool(d.get(CONF_WAKE_SIGNAL_ONLY, False)),
                tablet_low=int(d.get(CONF_TABLET_LOW, 40)),
                tablet_high=int(d.get(CONF_TABLET_HIGH, 80)),
                diffuser_on_minutes=int(d.get(CONF_DIFFUSER_ON_MIN, 15)),
                diffuser_off_minutes=int(d.get(CONF_DIFFUSER_OFF_MIN, 15)),
                manual_on_cooldown_seconds=int(d.get(CONF_MANUAL_COOLDOWN, 900)),
            )
            self.configs[cfg.device_id] = cfg

        self.states: dict[str, DeviceState] = {dev_id: DeviceState() for dev_id in self.configs}
        self.decisions: dict[str, Decision] = {}
        self.last_action: dict[str, dict[str, Any]] = {}

    # ---------- lifecycle ----------
    async def async_init(self) -> None:
        stored = await self._store.async_load() or {}
        for dev_id, persisted in (stored.get("devices") or {}).items():
            if dev_id in self.states:
                st = self.states[dev_id]
                st.manual_on_until_ts = persisted.get("manual_on_until_ts")
                st.diffuser_phase = persisted.get("diffuser_phase", "off")
                st.diffuser_phase_since_ts = persisted.get("diffuser_phase_since_ts", 0.0)
                st.suspended = persisted.get("suspended", False)
                self.last_action[dev_id] = persisted.get("last_action", {})

        if self.hass.is_running:
            self._ha_started = True
        else:
            self._unsub.append(
                self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, self._on_started)
            )

        watch = set()
        for v in self.global_entities.values():
            if v:
                watch.add(v)
        for cfg in self.configs.values():
            watch.add(cfg.switch_entity)
            if cfg.power_entity:
                watch.add(cfg.power_entity)
            if cfg.battery_entity:
                watch.add(cfg.battery_entity)

        if watch:
            self._unsub.append(
                async_track_state_change_event(self.hass, list(watch), self._on_state_change)
            )
        self._unsub.append(
            async_track_time_interval(
                self.hass, self._on_interval, timedelta(seconds=self.scan_interval)
            )
        )
        await self.async_evaluate_all()

    async def async_shutdown(self) -> None:
        for u in self._unsub:
            u()
        self._unsub.clear()
        await self._async_save()

    @callback
    def _on_started(self, _event) -> None:
        self._ha_started = True
        self.hass.async_create_task(self.async_evaluate_all(ha_just_started=True))

    @callback
    def _on_state_change(self, _event) -> None:
        self.hass.async_create_task(self.async_evaluate_all())

    @callback
    def _on_interval(self, _now) -> None:
        self.hass.async_create_task(self.async_evaluate_all())

    # ---------- read HA state into engine inputs ----------
    def _read_str(self, entity_id: str | None) -> str | None:
        if not entity_id:
            return None
        s = self.hass.states.get(entity_id)
        return s.state if s else None

    def _read_bool(self, entity_id: str | None) -> bool | None:
        s = self._read_str(entity_id)
        if s is None:
            return None
        return s.lower() in ("on", "true", "1", "active", "playing")

    def _build_context(self) -> GlobalContext:
        return GlobalContext(
            presence=self._read_str(self.global_entities["presence"]),
            bio=self._read_str(self.global_entities["bio"]),
            day_phase=self._read_str(self.global_entities["day"]),
            media_context=self._read_str(self.global_entities["media"]),
            entertainment_active=self._read_bool(self.global_entities["entertainment"]),
            activity=self._read_str(self.global_entities["activity"]),
            now_ts=dt_util.utcnow().timestamp(),
        )

    def _refresh_device_state(self, cfg: DeviceConfig) -> DeviceState:
        st = self.states[cfg.device_id]
        st.switch_state = self._read_str(cfg.switch_entity)
        st.power_w = self._read_str(cfg.power_entity) if cfg.power_entity else None
        st.battery_pct = self._read_str(cfg.battery_entity) if cfg.battery_entity else None
        return st

    # ---------- evaluation + actions ----------
    async def async_evaluate_all(self, *, ha_just_started: bool = False) -> None:
        ctx = self._build_context()
        for cfg in self.configs.values():
            st = self._refresh_device_state(cfg)
            decision = evaluate(cfg, st, ctx, ha_just_started=ha_just_started)
            self.decisions[cfg.device_id] = decision

            if cfg.kind == "diffuser" and decision.desired_switch_state in (DESIRED_ON, DESIRED_OFF):
                new_phase = "on" if decision.desired_switch_state == DESIRED_ON else "off"
                if st.diffuser_phase != new_phase:
                    st.diffuser_phase = new_phase
                    st.diffuser_phase_since_ts = ctx.now_ts

            if self.enable_control:
                await self._apply_decision(cfg, st, decision)

        await self._async_save()
        for cb in self._listeners:
            cb()

    async def _apply_decision(self, cfg: DeviceConfig, st: DeviceState, dec: Decision) -> None:
        if dec.desired_switch_state == DESIRED_KEEP:
            return
        target = "turn_on" if dec.desired_switch_state == DESIRED_ON else "turn_off"
        current = (st.switch_state or "").lower()
        if (target == "turn_on" and current == "on") or (target == "turn_off" and current == "off"):
            return
        try:
            await self.hass.services.async_call(
                "switch", target, {"entity_id": cfg.switch_entity}, blocking=False,
            )
            self.last_action[cfg.device_id] = {
                "action": target,
                "reason": dec.reason,
                "ts": dt_util.utcnow().isoformat(),
            }
            _LOGGER.info(
                "plug_policy_engine: %s on %s — %s", target, cfg.switch_entity, dec.reason,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "plug_policy_engine: switch call failed for %s: %s", cfg.switch_entity, err,
            )

    # ---------- service helpers ----------
    async def async_suspend(self, device_id: str, suspend: bool) -> None:
        if device_id in self.states:
            self.states[device_id].suspended = suspend
            await self.async_evaluate_all()

    async def async_mark_manual_on(self, device_id: str) -> None:
        if device_id not in self.states:
            return
        cfg = self.configs[device_id]
        self.states[device_id].manual_on_until_ts = (
            dt_util.utcnow().timestamp() + cfg.manual_on_cooldown_seconds
        )
        await self.async_evaluate_all()

    async def async_apply_now(self, device_id: str | None = None) -> None:
        prev = self.enable_control
        self.enable_control = True
        try:
            await self.async_evaluate_all()
        finally:
            self.enable_control = prev

    def add_listener(self, cb) -> None:
        self._listeners.append(cb)

    def remove_listener(self, cb) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    async def _async_save(self) -> None:
        await self._store.async_save({
            "devices": {
                dev_id: {
                    "manual_on_until_ts": st.manual_on_until_ts,
                    "diffuser_phase": st.diffuser_phase,
                    "diffuser_phase_since_ts": st.diffuser_phase_since_ts,
                    "suspended": st.suspended,
                    "last_action": self.last_action.get(dev_id, {}),
                }
                for dev_id, st in self.states.items()
            }
        })


# ----------------------------------------------------------------- lookups


def coordinator_from_hass(hass: HomeAssistant, entry_id: str) -> PlugPolicyCoordinator | None:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry_id)
    if not bucket:
        return None
    return bucket.get("coordinator")


def all_plug_policy_coordinators(hass: HomeAssistant) -> list[PlugPolicyCoordinator]:
    out: list[PlugPolicyCoordinator] = []
    for bucket in hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).values():
        if bucket.get("module_id") != MODULE_ID:
            continue
        c = bucket.get("coordinator")
        if c is not None:
            out.append(c)
    return out


def coordinator_for_device(hass: HomeAssistant, device_id: str) -> PlugPolicyCoordinator | None:
    for c in all_plug_policy_coordinators(hass):
        if device_id in c.configs:
            return c
    return None
