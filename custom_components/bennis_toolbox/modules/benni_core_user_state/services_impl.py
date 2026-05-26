"""Service-Handler des Benni Core · User State Moduls.

Registriert über die Umbrella unter `bennis_toolbox.benni_core_user_state_<action>`:

- `set_sleep`  — Sleep-Request, blockiert wenn PC aktiv (R-US-02)
- `set_waking` — WAKING-Signal, nur aus sleep (R-US-03)
- `set_awake`  — AWAKE-Signal, aus sleep oder waking (R-US-04)

Diese Services sind das Toolbox-Pendant zu den `script.system_mark_*`
aus einhornzentrale — aber sie fahren die LH-Regeln intern durch, statt
den Zustand blind zu setzen.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DATA_ENTRIES, DOMAIN
from ...services import ServiceDef
from .const import SERVICE_SET_AWAKE, SERVICE_SET_SLEEP, SERVICE_SET_WAKING
from .coordinator import UserStateCoordinator
from .logic import TriggerKind

_LOGGER = logging.getLogger(__name__)


def _all_coordinators(hass: HomeAssistant) -> list[UserStateCoordinator]:
    """Alle aktiven User-State-Coordinators (typisch genau einer — Single-Instance)."""
    buckets = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {})
    out: list[UserStateCoordinator] = []
    for bucket in buckets.values():
        coord = bucket.get("coordinator")
        if isinstance(coord, UserStateCoordinator):
            out.append(coord)
    return out


async def _apply_trigger(hass: HomeAssistant, kind: TriggerKind) -> None:
    coords = _all_coordinators(hass)
    if not coords:
        _LOGGER.warning(
            "service %s aufgerufen, aber kein User-State-Coordinator aktiv", kind.value
        )
        return
    for coord in coords:
        result = await coord.async_apply_service_trigger(kind)
        if result.trigger_blocked:
            _LOGGER.info(
                "service %s blockiert: %s", kind.value, result.trigger_blocked_reason
            )


async def _set_sleep(hass: HomeAssistant, _call: ServiceCall) -> None:
    await _apply_trigger(hass, TriggerKind.SLEEP_REQUEST)


async def _set_waking(hass: HomeAssistant, _call: ServiceCall) -> None:
    await _apply_trigger(hass, TriggerKind.WAKING_SIGNAL)


async def _set_awake(hass: HomeAssistant, _call: ServiceCall) -> None:
    await _apply_trigger(hass, TriggerKind.AWAKE_SIGNAL)


SERVICES: dict[str, ServiceDef] = {
    SERVICE_SET_SLEEP: ServiceDef(handler=_set_sleep),
    SERVICE_SET_WAKING: ServiceDef(handler=_set_waking),
    SERVICE_SET_AWAKE: ServiceDef(handler=_set_awake),
}
