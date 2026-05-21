"""Service-Dispatcher der Toolbox.

Module exportieren in ihrem `__init__.py` optional `SERVICES`:

    SERVICES: dict[str, ServiceDef] = {
        "set_plan": ServiceDef(schema=..., handler=async_set_plan),
        ...
    }

Die Toolbox registriert sie unter ihrer Domain mit präfixiertem Namen:

    bennis_toolbox.wake_planner_set_plan
    bennis_toolbox.title_classifier_classify
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, service_name
from .modules import REGISTERED_MODULE_IDS, load_module

_LOGGER = logging.getLogger(__name__)

ServiceHandler = Callable[[HomeAssistant, ServiceCall], Awaitable[Any]]


@dataclass(frozen=True)
class ServiceDef:
    handler: ServiceHandler
    schema: vol.Schema | None = None


async def async_register_all(hass: HomeAssistant) -> None:
    """Alle Modulservices unter `bennis_toolbox.<module>_<action>` registrieren.

    Wird nur einmal pro Toolbox-Lebenszeit aufgerufen. Defekte Module werden
    übersprungen.
    """
    for module_id in REGISTERED_MODULE_IDS:
        try:
            mod = await hass.async_add_executor_job(load_module, module_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("skip services for %s: %s", module_id, err)
            continue
        services: dict[str, ServiceDef] = getattr(mod, "SERVICES", {}) or {}
        for action, sdef in services.items():
            full = service_name(module_id, action)
            if hass.services.has_service(DOMAIN, full):
                continue

            async def _handle(call: ServiceCall, _h=sdef.handler) -> None:
                await _h(hass, call)

            hass.services.async_register(DOMAIN, full, _handle, schema=sdef.schema)
            _LOGGER.debug("registered service %s.%s", DOMAIN, full)


async def async_unregister_all(hass: HomeAssistant) -> None:
    for module_id in REGISTERED_MODULE_IDS:
        try:
            mod = await hass.async_add_executor_job(load_module, module_id)
        except Exception:  # noqa: BLE001
            continue
        services: dict[str, ServiceDef] = getattr(mod, "SERVICES", {}) or {}
        for action in services:
            full = service_name(module_id, action)
            if hass.services.has_service(DOMAIN, full):
                hass.services.async_remove(DOMAIN, full)
