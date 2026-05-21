"""Services des Notification-Router-Moduls.

Registriert unter `bennis_toolbox.notification_router_<action>`:
- route(event_type, severity?, title?, message?, payload?, dedupe_key?)
- clear(dedupe_key?)
- set_dnd(duration?)
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from ...services import ServiceDef
from .const import (
    EVENT_CLASSES,
    SERVICE_CLEAR,
    SERVICE_ROUTE,
    SERVICE_SET_DND,
    SEV_NORMAL,
    SEVERITIES,
)
from .coordinator import all_notification_routers


_ROUTE_SCHEMA = vol.Schema({
    vol.Required("event_type"): vol.In(EVENT_CLASSES),
    vol.Optional("severity", default=SEV_NORMAL): vol.In(SEVERITIES),
    vol.Optional("title", default=""): cv.string,
    vol.Optional("message", default=""): cv.string,
    vol.Optional("payload", default={}): dict,
    vol.Optional("dedupe_key"): cv.string,
})

_CLEAR_SCHEMA = vol.Schema({
    vol.Optional("dedupe_key"): cv.string,
})

_SET_DND_SCHEMA = vol.Schema({
    vol.Optional("duration", default=0): vol.All(int, vol.Range(min=0, max=86400)),
})


async def _route(hass: HomeAssistant, call: ServiceCall) -> None:
    for router in all_notification_routers(hass):
        await router.async_route(
            event_type=call.data["event_type"],
            severity=call.data.get("severity", SEV_NORMAL),
            title=call.data.get("title", ""),
            message=call.data.get("message", ""),
            payload=call.data.get("payload") or {},
            dedupe_key=call.data.get("dedupe_key"),
        )


async def _clear(hass: HomeAssistant, call: ServiceCall) -> None:
    for router in all_notification_routers(hass):
        await router.async_clear(call.data.get("dedupe_key"))


async def _set_dnd(hass: HomeAssistant, call: ServiceCall) -> None:
    duration = call.data.get("duration")
    for router in all_notification_routers(hass):
        await router.async_set_dnd(duration or None)


SERVICES: dict[str, ServiceDef] = {
    SERVICE_ROUTE: ServiceDef(handler=_route, schema=_ROUTE_SCHEMA),
    SERVICE_CLEAR: ServiceDef(handler=_clear, schema=_CLEAR_SCHEMA),
    SERVICE_SET_DND: ServiceDef(handler=_set_dnd, schema=_SET_DND_SCHEMA),
}
