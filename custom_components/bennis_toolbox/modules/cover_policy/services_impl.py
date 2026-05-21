"""Services für Cover Policy.

Registriert unter `bennis_toolbox.cover_policy_<action>`. Targeting:
optional per `entry_id`; ohne entry_id wird auf alle geladenen Coordinator
gefäht (nützlich für Multi-Cover).
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from ...services import ServiceDef
from .const import (
    PROFILE_MODES,
    SERVICE_APPLY_NOW,
    SERVICE_CLEAR_MANUAL_OVERRIDE,
    SERVICE_SET_MANUAL_OVERRIDE,
    SERVICE_SET_POSITION_PROFILE,
)
from .coordinator import all_cover_policy_coordinators, coordinator_from_hass


def _targets(hass: HomeAssistant, entry_id: str | None) -> list:
    if entry_id:
        c = coordinator_from_hass(hass, entry_id)
        return [c] if c else []
    return all_cover_policy_coordinators(hass)


_ENTRY_ONLY = vol.Schema({vol.Optional("entry_id"): cv.string})
_OVERRIDE_SCHEMA = vol.Schema({
    vol.Optional("entry_id"): cv.string,
    vol.Optional("duration"): vol.All(vol.Coerce(int), vol.Range(min=0, max=86400)),
})
_PROFILE_FIELD = vol.Schema(
    {vol.Optional(m): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)) for m in PROFILE_MODES}
)
_PROFILE_SCHEMA = vol.Schema({
    vol.Optional("entry_id"): cv.string,
    vol.Required("profile"): _PROFILE_FIELD,
})


async def _apply_now(hass: HomeAssistant, call: ServiceCall) -> None:
    for c in _targets(hass, call.data.get("entry_id")):
        await c.async_apply_now()


async def _set_override(hass: HomeAssistant, call: ServiceCall) -> None:
    duration = call.data.get("duration")
    for c in _targets(hass, call.data.get("entry_id")):
        await c.async_set_manual_override(duration)


async def _clear_override(hass: HomeAssistant, call: ServiceCall) -> None:
    for c in _targets(hass, call.data.get("entry_id")):
        await c.async_clear_manual_override()


async def _set_profile(hass: HomeAssistant, call: ServiceCall) -> None:
    profile = dict(call.data.get("profile") or {})
    for c in _targets(hass, call.data.get("entry_id")):
        await c.async_set_position_profile(profile)


SERVICES: dict[str, ServiceDef] = {
    SERVICE_APPLY_NOW: ServiceDef(handler=_apply_now, schema=_ENTRY_ONLY),
    SERVICE_SET_MANUAL_OVERRIDE: ServiceDef(handler=_set_override, schema=_OVERRIDE_SCHEMA),
    SERVICE_CLEAR_MANUAL_OVERRIDE: ServiceDef(handler=_clear_override, schema=_ENTRY_ONLY),
    SERVICE_SET_POSITION_PROFILE: ServiceDef(handler=_set_profile, schema=_PROFILE_SCHEMA),
}
