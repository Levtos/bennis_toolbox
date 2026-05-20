"""Domain services."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import BenniPlugCoordinator

SVC_FORCE_EVAL = "force_evaluate"
SVC_APPLY_NOW = "apply_policy_now"
SVC_SUSPEND = "suspend_device_policy"
SVC_RESUME = "resume_device_policy"
SVC_MARK_MANUAL = "set_manual_recently_on"

_DEVICE_SCHEMA = vol.Schema({vol.Required("device_id"): cv.string})


def _iter_coordinators(hass: HomeAssistant):
    for c in hass.data.get(DOMAIN, {}).values():
        if isinstance(c, BenniPlugCoordinator):
            yield c


def _find(hass: HomeAssistant, device_id: str) -> BenniPlugCoordinator | None:
    for c in _iter_coordinators(hass):
        if device_id in c.configs:
            return c
    return None


def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SVC_FORCE_EVAL):
        return

    async def force_evaluate(_call: ServiceCall) -> None:
        for c in _iter_coordinators(hass):
            await c.async_evaluate_all()

    async def apply_now(call: ServiceCall) -> None:
        dev_id = call.data.get("device_id")
        if dev_id:
            c = _find(hass, dev_id)
            if c:
                await c.async_apply_now(dev_id)
            return
        for c in _iter_coordinators(hass):
            await c.async_apply_now()

    async def suspend(call: ServiceCall) -> None:
        dev_id = call.data["device_id"]
        c = _find(hass, dev_id)
        if c:
            await c.async_suspend(dev_id, True)

    async def resume(call: ServiceCall) -> None:
        dev_id = call.data["device_id"]
        c = _find(hass, dev_id)
        if c:
            await c.async_suspend(dev_id, False)

    async def mark_manual(call: ServiceCall) -> None:
        dev_id = call.data["device_id"]
        c = _find(hass, dev_id)
        if c:
            await c.async_mark_manual_on(dev_id)

    hass.services.async_register(DOMAIN, SVC_FORCE_EVAL, force_evaluate)
    hass.services.async_register(
        DOMAIN, SVC_APPLY_NOW, apply_now,
        schema=vol.Schema({vol.Optional("device_id"): cv.string}),
    )
    hass.services.async_register(DOMAIN, SVC_SUSPEND, suspend, schema=_DEVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SVC_RESUME, resume, schema=_DEVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SVC_MARK_MANUAL, mark_manual, schema=_DEVICE_SCHEMA)


def async_unregister_services(hass: HomeAssistant) -> None:
    for svc in (SVC_FORCE_EVAL, SVC_APPLY_NOW, SVC_SUSPEND, SVC_RESUME, SVC_MARK_MANUAL):
        if hass.services.has_service(DOMAIN, svc):
            hass.services.async_remove(DOMAIN, svc)
