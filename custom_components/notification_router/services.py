"""Services for notification_router."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN, EVENT_CLASSES, SERVICE_CLEAR, SERVICE_ROUTE, SERVICE_SET_DND,
    SEV_NORMAL, SEVERITIES,
)

_LOGGER = logging.getLogger(__name__)

ROUTE_SCHEMA = vol.Schema({
    vol.Required("event_type"): vol.In(EVENT_CLASSES),
    vol.Optional("severity", default=SEV_NORMAL): vol.In(SEVERITIES),
    vol.Optional("title", default=""): cv.string,
    vol.Optional("message", default=""): cv.string,
    vol.Optional("payload", default={}): dict,
    vol.Optional("dedupe_key"): cv.string,
})

CLEAR_SCHEMA = vol.Schema({
    vol.Optional("dedupe_key"): cv.string,
})

SET_DND_SCHEMA = vol.Schema({
    vol.Optional("duration", default=0): vol.All(int, vol.Range(min=0, max=86400)),
})


def _routers(hass: HomeAssistant):
    return list(hass.data.get(DOMAIN, {}).values())


async def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_ROUTE):
        return

    async def handle_route(call: ServiceCall) -> None:
        for router in _routers(hass):
            await router.async_route(
                event_type=call.data["event_type"],
                severity=call.data.get("severity", SEV_NORMAL),
                title=call.data.get("title", ""),
                message=call.data.get("message", ""),
                payload=call.data.get("payload") or {},
                dedupe_key=call.data.get("dedupe_key"),
            )

    async def handle_clear(call: ServiceCall) -> None:
        for router in _routers(hass):
            await router.async_clear(call.data.get("dedupe_key"))

    async def handle_set_dnd(call: ServiceCall) -> None:
        for router in _routers(hass):
            await router.async_set_dnd(call.data.get("duration") or None)

    hass.services.async_register(DOMAIN, SERVICE_ROUTE, handle_route, schema=ROUTE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, handle_clear, schema=CLEAR_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_DND, handle_set_dnd, schema=SET_DND_SCHEMA)


async def async_unregister_services(hass: HomeAssistant) -> None:
    for svc in (SERVICE_ROUTE, SERVICE_CLEAR, SERVICE_SET_DND):
        if hass.services.has_service(DOMAIN, svc):
            hass.services.async_remove(DOMAIN, svc)
