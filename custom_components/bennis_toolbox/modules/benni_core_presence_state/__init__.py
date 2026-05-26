"""Modul: Benni Core · Presence State.

Status: PENDING (Skelett — wird Schritt für Schritt auf READY gehoben).

Drittes der drei "Herzen" der benni_core-Architektur. Liefert
`sensor.benni_core_presence_*` + `binary_sensor.benni_core_presence_preheat_active`
nach Lastenheft Context State v1.1 §4.2-4.5 und R-PS-01..R-PS-11.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .coordinator import PresenceStateCoordinator
from .entities import async_get_entities  # re-export
from .flow import ConfigFlowHelper, OptionsFlowHelper  # re-export

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "SPEC",
    "ConfigFlowHelper",
    "OptionsFlowHelper",
    "async_setup_entry",
    "async_unload_entry",
    "async_get_entities",
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = PresenceStateCoordinator(hass, entry)
    await coordinator.async_load_stored()
    await coordinator.async_config_entry_first_refresh()

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["coordinator"] = coordinator

    coordinator.async_start_listeners()
    entry.async_on_unload(coordinator.async_stop_listeners)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    coordinator: PresenceStateCoordinator | None = (
        bucket.pop("coordinator", None) if bucket else None
    )
    if coordinator is not None:
        coordinator.async_stop_listeners()
    return True
