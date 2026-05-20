"""Services des Benni-Media-Context-Moduls.

Registriert über die Umbrella unter `bennis_toolbox.benni_media_context_<action>`.
`start_radio` und `stop_media` feuern Toolbox-Events; Automations können daran
hängen.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from ...services import ServiceDef
from .const import (
    EVENT_START_RADIO,
    EVENT_STOP_MEDIA,
    SERVICE_CLEAR_MANUAL_NUDGE,
    SERVICE_FORCE_RECALCULATE,
    SERVICE_SET_MANUAL_NUDGE,
    SERVICE_START_RADIO,
    SERVICE_STOP_MEDIA,
)
from .coordinator import all_benni_media_context_coordinators


_NUDGE_SCHEMA = vol.Schema({vol.Required("subcontext"): cv.string})
_RADIO_SCHEMA = vol.Schema({vol.Optional("station"): cv.string})
_STOP_SCHEMA = vol.Schema({})


async def _force(hass: HomeAssistant, _call: ServiceCall) -> None:
    for c in all_benni_media_context_coordinators(hass):
        await c.async_recalculate()


async def _set_nudge(hass: HomeAssistant, call: ServiceCall) -> None:
    sub = call.data["subcontext"]
    for c in all_benni_media_context_coordinators(hass):
        c.set_manual_nudge(sub)


async def _clear_nudge(hass: HomeAssistant, _call: ServiceCall) -> None:
    for c in all_benni_media_context_coordinators(hass):
        c.clear_manual_nudge()


async def _start_radio(hass: HomeAssistant, call: ServiceCall) -> None:
    hass.bus.async_fire(EVENT_START_RADIO, {"station": call.data.get("station")})


async def _stop_media(hass: HomeAssistant, _call: ServiceCall) -> None:
    hass.bus.async_fire(EVENT_STOP_MEDIA, {})


SERVICES: dict[str, ServiceDef] = {
    SERVICE_FORCE_RECALCULATE: ServiceDef(handler=_force),
    SERVICE_SET_MANUAL_NUDGE: ServiceDef(handler=_set_nudge, schema=_NUDGE_SCHEMA),
    SERVICE_CLEAR_MANUAL_NUDGE: ServiceDef(handler=_clear_nudge),
    SERVICE_START_RADIO: ServiceDef(handler=_start_radio, schema=_RADIO_SCHEMA),
    SERVICE_STOP_MEDIA: ServiceDef(handler=_stop_media, schema=_STOP_SCHEMA),
}
