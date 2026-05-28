"""Modul: Benni Core · Devices.

Foundation-Modul. Multi-Instance: pro physischem Gerät ein Config-Entry.
Liefert pro Device einen Hauptsensor `sensor.benni_device_<slug>` mit
konsolidiertem State und Standard-Attribut-Schema laut LH device_core v0.2.

- unique_id-Präfix:  `bennis_toolbox_benni_core_devices_*`
- Services:          `bennis_toolbox.benni_core_devices_set_override` etc.
- Storage:           `.storage/bennis_toolbox_benni_core_devices_state_<entry_id>`
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .coordinator import DeviceCoordinator
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
    coordinator = DeviceCoordinator(hass, entry)
    await coordinator.async_load_stored()
    await coordinator.async_config_entry_first_refresh()

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["coordinator"] = coordinator

    coordinator.async_start_listeners()
    entry.async_on_unload(coordinator.async_stop_listeners)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    coordinator: DeviceCoordinator | None = (
        bucket.pop("coordinator", None) if bucket else None
    )
    if coordinator is not None:
        coordinator.async_stop_listeners()
    return True
