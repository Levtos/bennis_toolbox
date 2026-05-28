"""Service-Handler für Benni Core · Devices.

Registriert über die Umbrella unter `bennis_toolbox.benni_core_devices_<action>`:

- `set_override`   — R-DC-07: powered/power_state für ein Device festsetzen
- `clear_override` — R-DC-07: Override entfernen

Der Bulk-Import (R-DC-08) läuft NICHT über einen Service, sondern über den
Config-Flow (Menü "Bulk-Import (YAML)" beim Hinzufügen) — siehe flow.py.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall

from ...services import ServiceDef
from .const import (
    ATTR_EXPIRE_SECONDS,
    ATTR_POWER_STATE,
    ATTR_POWERED,
    ATTR_SLUG,
    POWER_STATE_SLUGS,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_SET_OVERRIDE,
)
from .coordinator import coordinator_by_slug

_LOGGER = logging.getLogger(__name__)


_SET_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SLUG): str,
        vol.Optional(ATTR_POWERED): vol.Any(bool, None),
        vol.Optional(ATTR_POWER_STATE): vol.Any(vol.In(POWER_STATE_SLUGS), None),
        vol.Optional(ATTR_EXPIRE_SECONDS): vol.Any(
            vol.All(int, vol.Range(min=1, max=86400 * 30)), None
        ),
    }
)

_CLEAR_OVERRIDE_SCHEMA = vol.Schema({vol.Required(ATTR_SLUG): str})


async def _set_override(hass: HomeAssistant, call: ServiceCall) -> None:
    slug = call.data[ATTR_SLUG]
    coord = coordinator_by_slug(hass, slug)
    if coord is None:
        _LOGGER.warning("set_override: unknown device slug %r", slug)
        return
    await coord.async_set_override(
        powered=call.data.get(ATTR_POWERED),
        power_state=call.data.get(ATTR_POWER_STATE),
        expire_seconds=call.data.get(ATTR_EXPIRE_SECONDS),
    )


async def _clear_override(hass: HomeAssistant, call: ServiceCall) -> None:
    slug = call.data[ATTR_SLUG]
    coord = coordinator_by_slug(hass, slug)
    if coord is None:
        _LOGGER.warning("clear_override: unknown device slug %r", slug)
        return
    await coord.async_clear_override()


SERVICES: dict[str, ServiceDef] = {
    SERVICE_SET_OVERRIDE: ServiceDef(
        handler=_set_override, schema=_SET_OVERRIDE_SCHEMA
    ),
    SERVICE_CLEAR_OVERRIDE: ServiceDef(
        handler=_clear_override, schema=_CLEAR_OVERRIDE_SCHEMA
    ),
}
