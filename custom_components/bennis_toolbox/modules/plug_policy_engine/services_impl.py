"""Service-Handler des Plug-Policy-Engine-Moduls.

Registriert unter `bennis_toolbox.plug_policy_engine_<action>`.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from ...services import ServiceDef
from .const import (
    SERVICE_APPLY_NOW,
    SERVICE_FORCE_EVAL,
    SERVICE_MARK_MANUAL,
    SERVICE_RESUME,
    SERVICE_SUSPEND,
)
from .coordinator import all_plug_policy_coordinators, coordinator_for_device


_DEVICE_SCHEMA = vol.Schema({vol.Required("device_id"): cv.string})


async def _force(hass: HomeAssistant, _call: ServiceCall) -> None:
    for c in all_plug_policy_coordinators(hass):
        await c.async_evaluate_all()


async def _apply_now(hass: HomeAssistant, call: ServiceCall) -> None:
    dev_id = call.data.get("device_id")
    if dev_id:
        c = coordinator_for_device(hass, dev_id)
        if c:
            await c.async_apply_now(dev_id)
        return
    for c in all_plug_policy_coordinators(hass):
        await c.async_apply_now()


async def _suspend(hass: HomeAssistant, call: ServiceCall) -> None:
    dev_id = call.data["device_id"]
    c = coordinator_for_device(hass, dev_id)
    if c:
        await c.async_suspend(dev_id, True)


async def _resume(hass: HomeAssistant, call: ServiceCall) -> None:
    dev_id = call.data["device_id"]
    c = coordinator_for_device(hass, dev_id)
    if c:
        await c.async_suspend(dev_id, False)


async def _mark_manual(hass: HomeAssistant, call: ServiceCall) -> None:
    dev_id = call.data["device_id"]
    c = coordinator_for_device(hass, dev_id)
    if c:
        await c.async_mark_manual_on(dev_id)


SERVICES: dict[str, ServiceDef] = {
    SERVICE_FORCE_EVAL: ServiceDef(handler=_force),
    SERVICE_APPLY_NOW: ServiceDef(
        handler=_apply_now,
        schema=vol.Schema({vol.Optional("device_id"): cv.string}),
    ),
    SERVICE_SUSPEND: ServiceDef(handler=_suspend, schema=_DEVICE_SCHEMA),
    SERVICE_RESUME: ServiceDef(handler=_resume, schema=_DEVICE_SCHEMA),
    SERVICE_MARK_MANUAL: ServiceDef(handler=_mark_manual, schema=_DEVICE_SCHEMA),
}
