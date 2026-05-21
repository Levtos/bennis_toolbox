"""Runtime / coordinator des Notification-Router-Moduls.

Cross-Modul-Inputs (Bio/Activity/Presence/Quiet/Headset/Media von
benni_context, benni_media_context, plug_policy_engine …) werden
ausschließlich als HA-Entity-IDs aus der Konfig konsumiert — kein Python-
Cross-Modul-Import.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, time as dtime
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from ...const import DATA_ENTRIES, DOMAIN
from ...storage import make_store
from .const import (
    CONF_ACTIVITY_STATE,
    CONF_BIO_STATE,
    CONF_DOORBELL_STATE,
    CONF_HEADSET_ACTIVE,
    CONF_LIGHT_SCRIPT,
    CONF_LOCK_BATTERY,
    CONF_MEDIA_CONTEXT,
    CONF_MEDIA_SCRIPT,
    CONF_NOTIFY_TARGETS,
    CONF_OPENING_SAFETY,
    CONF_PRESENCE_PERSONAL,
    CONF_QUIET_MODE_ACTIVE,
    DEFAULT_COOLDOWNS,
    DEFAULT_RATE_LIMIT,
    EVENT_CLASSES,
    EVENT_ROUTED,
    MODULE_ID,
    OPT_COOLDOWNS,
    OPT_QUIET_HOURS_END,
    OPT_QUIET_HOURS_START,
    OPT_RATE_LIMIT,
    OPT_SEVERITY_MAP,
    ROUTE_BUS_ONLY,
    ROUTE_DASHBOARD,
    ROUTE_LIGHT,
    ROUTE_MEDIA,
    ROUTE_PERSISTENT,
    ROUTE_PUSH,
    SEV_NORMAL,
    SEVERITIES,
    STORAGE_VERSION,
)
from .routing import Context, Decision, Event, decide

_LOGGER = logging.getLogger(__name__)

# Dispatcher signal that entities subscribe to.
SIGNAL_STATE_UPDATED = f"bennis_toolbox_{MODULE_ID}_state_updated"


def _parse_hhmm(value: str | None) -> dtime | None:
    if not value:
        return None
    try:
        hh, mm = value.split(":")[:2]
        return dtime(int(hh), int(mm))
    except (ValueError, AttributeError):
        return None


def _in_quiet_hours(now: datetime, start: dtime | None, end: dtime | None) -> bool:
    if start is None or end is None:
        return False
    t = now.time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end


class NotificationRouter:
    """Hält Runtime-State und exponiert Routing-Entrypoints."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        entry_data: dict[str, Any],
        options: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.data = entry_data
        self.options = options
        self._store = make_store(
            hass, MODULE_ID, f"state_{entry_id}", version=STORAGE_VERSION
        )
        self._dedupe: dict[str, float] = {}
        self._cooldowns: dict[str, float] = {}
        self._rate_window: deque[float] = deque(maxlen=200)
        self._dnd_until: float | None = None
        self._last_decision: Decision | None = None
        self._last_event: Event | None = None

    # ----- persistence -----
    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self._dedupe = dict(data.get("dedupe", {}))
        self._cooldowns = dict(data.get("cooldowns", {}))
        self._dnd_until = data.get("dnd_until")

    async def _async_save(self) -> None:
        await self._store.async_save({
            "dedupe": self._dedupe,
            "cooldowns": self._cooldowns,
            "dnd_until": self._dnd_until,
        })

    # ----- DND -----
    def dnd_active(self) -> bool:
        return self._dnd_until is not None and time.time() < self._dnd_until

    async def async_set_dnd(self, duration_seconds: int | None) -> None:
        if duration_seconds and duration_seconds > 0:
            self._dnd_until = time.time() + duration_seconds
        else:
            self._dnd_until = None
        await self._async_save()
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED)

    async def async_clear(self, dedupe_key: str | None = None) -> None:
        if dedupe_key:
            self._dedupe.pop(dedupe_key, None)
        else:
            self._dedupe.clear()
            self._cooldowns.clear()
        await self._async_save()
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED)

    # ----- context snapshot -----
    def _state(self, entity_id: str | None) -> str | None:
        if not entity_id:
            return None
        st = self.hass.states.get(entity_id)
        return st.state if st else None

    def _bool_state(self, entity_id: str | None) -> bool:
        s = self._state(entity_id)
        return s in ("on", "true", "True", "1", "home")

    def build_context(self) -> Context:
        opts = self.options
        start = _parse_hhmm(opts.get(OPT_QUIET_HOURS_START))
        end = _parse_hhmm(opts.get(OPT_QUIET_HOURS_END))
        now = datetime.now()
        return Context(
            bio_state=self._state(self.data.get(CONF_BIO_STATE)),
            activity_state=self._state(self.data.get(CONF_ACTIVITY_STATE)),
            presence=self._state(self.data.get(CONF_PRESENCE_PERSONAL)),
            media_active=self._bool_state(self.data.get(CONF_MEDIA_CONTEXT)),
            headset_active=self._bool_state(self.data.get(CONF_HEADSET_ACTIVE)),
            quiet_mode_active=self._bool_state(self.data.get(CONF_QUIET_MODE_ACTIVE)),
            doorbell_state=self._state(self.data.get(CONF_DOORBELL_STATE)),
            opening_safety=self._state(self.data.get(CONF_OPENING_SAFETY)),
            lock_battery_low=self._battery_low(),
            dnd_override=self.dnd_active(),
            in_quiet_hours=_in_quiet_hours(now, start, end),
        )

    def _battery_low(self) -> bool:
        ent = self.data.get(CONF_LOCK_BATTERY)
        s = self._state(ent)
        if s is None:
            return False
        try:
            return float(s) < 20.0
        except ValueError:
            return s in ("low", "critical", "on")

    # ----- gating helpers (pure-ish) -----
    def _check_rate(self) -> bool:
        limit = int(self.options.get(OPT_RATE_LIMIT, DEFAULT_RATE_LIMIT))
        now = time.time()
        while self._rate_window and now - self._rate_window[0] > 60:
            self._rate_window.popleft()
        if len(self._rate_window) >= limit:
            return False
        self._rate_window.append(now)
        return True

    def _check_dedupe(self, key: str | None) -> bool:
        if not key:
            return True
        last = self._dedupe.get(key)
        now = time.time()
        if last and now - last < 60:
            return False
        self._dedupe[key] = now
        return True

    def _check_cooldown(self, event_class: str) -> bool:
        cooldowns = {**DEFAULT_COOLDOWNS, **(self.options.get(OPT_COOLDOWNS) or {})}
        cd = int(cooldowns.get(event_class, 0))
        if cd <= 0:
            return True
        now = time.time()
        last = self._cooldowns.get(event_class, 0)
        if now - last < cd:
            return False
        self._cooldowns[event_class] = now
        return True

    # ----- routing entrypoint -----
    async def async_route(
        self,
        event_type: str,
        severity: str = SEV_NORMAL,
        title: str = "",
        message: str = "",
        payload: dict[str, Any] | None = None,
        dedupe_key: str | None = None,
    ) -> Decision:
        if event_type not in EVENT_CLASSES:
            _LOGGER.warning("Unknown event_type %s", event_type)
        if severity not in SEVERITIES:
            severity = SEV_NORMAL

        sev_map = self.options.get(OPT_SEVERITY_MAP) or {}
        severity = sev_map.get(event_type, severity)

        ev = Event(
            event_type=event_type,
            severity=severity,
            title=title,
            message=message,
            payload=payload or {},
            dedupe_key=dedupe_key,
        )

        suppression_reasons: list[str] = []
        if not self._check_rate():
            suppression_reasons.append("rate limit exceeded")
        if not self._check_dedupe(dedupe_key):
            suppression_reasons.append(f"dedupe_key={dedupe_key} within window")
        if not self._check_cooldown(event_type):
            suppression_reasons.append(f"cooldown for {event_type}")

        ctx = self.build_context()
        decision = decide(ev, ctx)

        if suppression_reasons:
            decision.routes = [
                r for r in decision.routes if r in (ROUTE_DASHBOARD, ROUTE_BUS_ONLY)
            ]
            decision.reason = decision.reason + "; suppressed: " + ", ".join(suppression_reasons)
            decision.mode = "silent" if not decision.routes else decision.mode

        self._last_decision = decision
        self._last_event = ev

        # Toolbox-prefixed event on the HA bus.
        self.hass.bus.async_fire(EVENT_ROUTED, {
            "event_type": event_type,
            "severity": decision.severity,
            "mode": decision.mode,
            "routes": decision.routes,
            "suppressed_routes": decision.suppressed_routes,
            "reason": decision.reason,
            "title": decision.title,
            "message": decision.message,
            "payload": ev.payload,
            "dedupe_key": dedupe_key,
            "masked": decision.masked,
            "context": decision.context,
        })

        await self._dispatch(decision, ev)
        await self._async_save()
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED)
        return decision

    async def _dispatch(self, decision: Decision, ev: Event) -> None:
        """Execute concrete output targets if configured. Non-blocking."""
        targets: list[str] = self.data.get(CONF_NOTIFY_TARGETS) or []
        light_script: str | None = self.data.get(CONF_LIGHT_SCRIPT)
        media_script: str | None = self.data.get(CONF_MEDIA_SCRIPT)

        for route in decision.routes:
            try:
                if route == ROUTE_PUSH and targets:
                    for svc in targets:
                        if "." not in svc:
                            continue
                        d, name = svc.split(".", 1)
                        await self.hass.services.async_call(
                            d, name,
                            {"title": decision.title, "message": decision.message},
                            blocking=False,
                        )
                elif route == ROUTE_PERSISTENT:
                    await self.hass.services.async_call(
                        "persistent_notification", "create",
                        {
                            "title": decision.title or "Notification Router",
                            "message": decision.message,
                            "notification_id": ev.dedupe_key
                                or f"{ev.event_type}_{int(time.time())}",
                        },
                        blocking=False,
                    )
                elif route == ROUTE_LIGHT and light_script:
                    await self._call_script(
                        light_script,
                        {"severity": decision.severity, "event_type": ev.event_type},
                    )
                elif route == ROUTE_MEDIA and media_script:
                    await self._call_script(
                        media_script,
                        {"title": decision.title, "message": decision.message},
                    )
            except Exception:  # noqa: BLE001 - never let one route break others
                _LOGGER.exception("Route %s dispatch failed", route)

    async def _call_script(self, entity_id: str, variables: dict[str, Any]) -> None:
        if "." not in entity_id:
            return
        d, obj = entity_id.split(".", 1)
        if d == "script":
            await self.hass.services.async_call("script", obj, variables, blocking=False)
        else:
            await self.hass.services.async_call(
                d, "turn_on", {"entity_id": entity_id}, blocking=False,
            )

    # ----- accessors -----
    @property
    def last_decision(self) -> Decision | None:
        return self._last_decision

    @property
    def last_event(self) -> Event | None:
        return self._last_event

    @callback
    def update_options(self, options: dict[str, Any]) -> None:
        self.options = options


# ------------------------------------------------------------------- lookups


def router_from_hass(hass: HomeAssistant, entry_id: str) -> NotificationRouter | None:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry_id)
    return bucket.get("router") if bucket else None


def all_notification_routers(hass: HomeAssistant) -> list[NotificationRouter]:
    out: list[NotificationRouter] = []
    for bucket in hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).values():
        if bucket.get("module_id") != MODULE_ID:
            continue
        r = bucket.get("router")
        if r is not None:
            out.append(r)
    return out
