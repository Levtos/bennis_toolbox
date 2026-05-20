"""Services for manual bio overrides.

Bio is the single source of truth for sleep / waking / awake, but the user
needs a manual override for edge cases (e.g. sick day, manual "I'm going to
bed now"). These services patch the persistent state and trigger a refresh.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import BIO_AWAKE, BIO_SLEEP, BIO_STATES, BIO_WAKING, DOMAIN
from .coordinator import BenniContextCoordinator

SERVICE_SET_BIO = "set_bio_state"
SERVICE_MARK_SLEEP = "mark_sleep"
SERVICE_MARK_AWAKE = "mark_awake"

SET_BIO_SCHEMA = vol.Schema({vol.Required("state"): vol.In(BIO_STATES)})


def _coordinators(hass: HomeAssistant) -> list[BenniContextCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


async def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_BIO):
        return

    async def _set_bio(call: ServiceCall) -> None:
        target = call.data["state"]
        now = dt_util.utcnow().isoformat()
        for c in _coordinators(hass):
            c._persistent.bio_state = target
            if target == BIO_SLEEP:
                c._persistent.last_sleep_start = now
            elif target == BIO_AWAKE:
                c._persistent.last_awake_start = now
            await c.async_request_refresh()

    async def _mark_sleep(call: ServiceCall) -> None:
        await _set_bio(ServiceCall(DOMAIN, SERVICE_SET_BIO, {"state": BIO_SLEEP}))

    async def _mark_awake(call: ServiceCall) -> None:
        await _set_bio(ServiceCall(DOMAIN, SERVICE_SET_BIO, {"state": BIO_AWAKE}))

    hass.services.async_register(
        DOMAIN, SERVICE_SET_BIO, _set_bio, schema=SET_BIO_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_MARK_SLEEP, _mark_sleep)
    hass.services.async_register(DOMAIN, SERVICE_MARK_AWAKE, _mark_awake)
