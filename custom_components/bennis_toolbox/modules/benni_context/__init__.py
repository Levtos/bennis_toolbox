"""Modul: Benni Context.

Status: READY. Fachlicher Owner für presence / bio / day / activity /
master-context. Wake Planner / Title Classifier werden ausschließlich als
konfigurierte HA-Entities konsumiert — keine direkten Cross-Modul-Imports.

- unique_id-Präfix:  `bennis_toolbox_benni_context_*`
- Services:          `bennis_toolbox.benni_context_*`
- Storage:           `.storage/bennis_toolbox_benni_context_state_<entry_id>`
- Keine WebSocket-Befehle, kein Panel.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .coordinator import BenniContextCoordinator
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
    coordinator = BenniContextCoordinator(hass, entry)
    await coordinator.async_load_stored()
    await coordinator.async_config_entry_first_refresh()

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["coordinator"] = coordinator

    coordinator.async_start_listeners()
    entry.async_on_unload(coordinator.async_stop_listeners)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    coordinator: BenniContextCoordinator | None = (
        bucket.pop("coordinator", None) if bucket else None
    )
    if coordinator is not None:
        coordinator.async_stop_listeners()
    return True
