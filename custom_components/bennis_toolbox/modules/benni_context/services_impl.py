"""Service-Handler des Benni-Context-Moduls.

Registriert über die Umbrella unter `bennis_toolbox.benni_context_<action>`:
- set_bio_state(state)  — patcht den persistierten Bio-Zustand und triggert Refresh.
- mark_sleep            — Shortcut für set_bio_state(sleep).
- mark_awake            — Shortcut für set_bio_state(awake).
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util

from ...services import ServiceDef
from .const import (
    BIO_AWAKE,
    BIO_SLEEP,
    BIO_STATES,
    SERVICE_MARK_AWAKE,
    SERVICE_MARK_SLEEP,
    SERVICE_SET_BIO,
)
from .coordinator import all_benni_context_coordinators


SET_BIO_SCHEMA = vol.Schema({vol.Required("state"): vol.In(BIO_STATES)})


async def _apply_bio(hass: HomeAssistant, target: str) -> None:
    now_iso = dt_util.utcnow().isoformat()
    for coord in all_benni_context_coordinators(hass):
        coord._persistent.bio_state = target
        if target == BIO_SLEEP:
            coord._persistent.last_sleep_start = now_iso
        elif target == BIO_AWAKE:
            coord._persistent.last_awake_start = now_iso
        await coord.async_request_refresh()


async def _set_bio(hass: HomeAssistant, call: ServiceCall) -> None:
    await _apply_bio(hass, call.data["state"])


async def _mark_sleep(hass: HomeAssistant, _call: ServiceCall) -> None:
    await _apply_bio(hass, BIO_SLEEP)


async def _mark_awake(hass: HomeAssistant, _call: ServiceCall) -> None:
    await _apply_bio(hass, BIO_AWAKE)


SERVICES: dict[str, ServiceDef] = {
    SERVICE_SET_BIO: ServiceDef(handler=_set_bio, schema=SET_BIO_SCHEMA),
    SERVICE_MARK_SLEEP: ServiceDef(handler=_mark_sleep),
    SERVICE_MARK_AWAKE: ServiceDef(handler=_mark_awake),
}
