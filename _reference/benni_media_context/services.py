"""Services."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_FORCE_RECALCULATE,
    SERVICE_SET_MANUAL_NUDGE,
    SERVICE_CLEAR_MANUAL_NUDGE,
    SERVICE_START_RADIO,
    SERVICE_STOP_MEDIA,
)

_NUDGE_SCHEMA = vol.Schema({vol.Required("subcontext"): cv.string})
_RADIO_SCHEMA = vol.Schema({vol.Optional("station"): cv.string})
_STOP_SCHEMA = vol.Schema({})


def _coords(hass: HomeAssistant):
    return list(hass.data.get(DOMAIN, {}).values())


def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_FORCE_RECALCULATE):
        return

    async def _force(call: ServiceCall):
        for c in _coords(hass):
            await c.async_recalculate()

    async def _set_nudge(call: ServiceCall):
        sub = call.data["subcontext"]
        for c in _coords(hass):
            c.set_manual_nudge(sub)

    async def _clear_nudge(call: ServiceCall):
        for c in _coords(hass):
            c.clear_manual_nudge()

    async def _start_radio(call: ServiceCall):
        # placeholder: emit event for automations to handle
        hass.bus.async_fire(f"{DOMAIN}_start_radio", {"station": call.data.get("station")})

    async def _stop_media(call: ServiceCall):
        hass.bus.async_fire(f"{DOMAIN}_stop_media", {})

    hass.services.async_register(DOMAIN, SERVICE_FORCE_RECALCULATE, _force)
    hass.services.async_register(DOMAIN, SERVICE_SET_MANUAL_NUDGE, _set_nudge, schema=_NUDGE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_MANUAL_NUDGE, _clear_nudge)
    hass.services.async_register(DOMAIN, SERVICE_START_RADIO, _start_radio, schema=_RADIO_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP_MEDIA, _stop_media, schema=_STOP_SCHEMA)


def async_unregister_services(hass: HomeAssistant) -> None:
    for s in (
        SERVICE_FORCE_RECALCULATE, SERVICE_SET_MANUAL_NUDGE, SERVICE_CLEAR_MANUAL_NUDGE,
        SERVICE_START_RADIO, SERVICE_STOP_MEDIA,
    ):
        if hass.services.has_service(DOMAIN, s):
            hass.services.async_remove(DOMAIN, s)
