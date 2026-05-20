"""Modul: Plug Policy Engine.

Status: READY. Policy-getriebenes Schalten von Steckdosen unter der
einen HA-Domain `bennis_toolbox`. Konsumiert Context/Media/Wake/Title-
Classifier-Outputs ausschließlich über vom Nutzer im Config-Flow gewählte
HA-Entity-IDs — keine Python-Cross-Modul-Imports.

- unique_id-Präfix: `bennis_toolbox_plug_policy_engine_*`
- Services:         `bennis_toolbox.plug_policy_engine_*`
- Storage:          `.storage/bennis_toolbox_plug_policy_engine_state_<entry_id>`
- Keine WebSocket-Befehle, kein Panel.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .coordinator import PlugPolicyCoordinator
from .entities import async_get_entities  # re-export
from .flow import ConfigFlowHelper, OptionsFlowHelper  # re-export
from .services_impl import SERVICES  # re-export

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "SPEC",
    "SERVICES",
    "ConfigFlowHelper",
    "OptionsFlowHelper",
    "async_setup_entry",
    "async_unload_entry",
    "async_get_entities",
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coord = PlugPolicyCoordinator(hass, entry)
    await coord.async_init()

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["coordinator"] = coord
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    coord: PlugPolicyCoordinator | None = bucket.pop("coordinator", None) if bucket else None
    if coord is not None:
        await coord.async_shutdown()
    return True
