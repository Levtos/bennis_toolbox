"""Modul: Cover Policy.

Policy-Engine für Rollos/Jalousien unter der einen HA-Domain
`bennis_toolbox`. Konsumiert Context- und Sensor-Outputs ausschließlich
als HA-Entity-IDs aus dem Config-Flow — kein Python-Cross-Modul-Import.

- unique_id-Präfix: `bennis_toolbox_cover_policy_*`
- Services:         `bennis_toolbox.cover_policy_*`
- Storage:          `.storage/bennis_toolbox_cover_policy_state_<entry_id>`
- Kein WebSocket, kein Panel.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .coordinator import CoverPolicyCoordinator
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
    coord = CoverPolicyCoordinator(hass, entry)
    await coord.async_load()
    coord.async_start()
    # Erste Auswertung; wird vom startup-Block oft als apply_allowed=False
    # markiert sein, das ist gewollt.
    await coord.async_evaluate()

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["coordinator"] = coord

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    coord: CoverPolicyCoordinator | None = bucket.pop("coordinator", None) if bucket else None
    if coord is not None:
        coord.async_stop()
    return True
