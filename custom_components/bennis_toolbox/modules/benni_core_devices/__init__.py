"""Modul: Benni Core · Devices (Single-Hub-Architektur).

EIN Config-Entry = der Hub "Benni Core · Devices". Die einzelnen Geräte
leben in `entry.options["devices"]` (Dict slug → device_conf) und werden
über den Options-Flow verwaltet (hinzufügen/bearbeiten/entfernen).

Pro Gerät:
- ein DeviceCoordinator (eigener Storage für Override/Sticky-Hold)
- ein HA-Device (DeviceInfo) unter dem Hub-Gerät (via_device)
- Haupt-Sensor `sensor.benni_device_<slug>` + optional Sekundär-Sensoren

- unique_id-Präfix:  `bennis_toolbox_benni_core_devices_*`
- Services:          `bennis_toolbox.benni_core_devices_set_override` etc.
- Storage:           `.storage/bennis_toolbox_benni_core_devices_state_<entry>_<slug>`
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .const import CONF_DEVICES, MODULE_ID, NAME
from .coordinator import DeviceCoordinator
from .entities import async_get_entities  # re-export
from .flow import ConfigFlowHelper, OptionsFlowHelper  # re-export
from .services_impl import SERVICES  # re-export

_LOGGER = logging.getLogger(__name__)

# Stabile Identifier des Hub-Geräts (alle Geräte hängen via_device daran).
HUB_IDENTIFIER = (DOMAIN, f"{MODULE_ID}_hub")

__all__ = [
    "SPEC",
    "SERVICES",
    "ConfigFlowHelper",
    "OptionsFlowHelper",
    "HUB_IDENTIFIER",
    "async_setup_entry",
    "async_unload_entry",
    "async_get_entities",
]


def _devices_conf(entry: ConfigEntry) -> dict[str, dict[str, Any]]:
    raw = entry.options.get(CONF_DEVICES)
    return dict(raw) if isinstance(raw, dict) else {}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Hub-Gerät registrieren, damit Geräte sich darunter einhängen können.
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={HUB_IDENTIFIER},
        name=NAME,
        manufacturer="Benni's Toolbox",
        model="Device Core Hub",
        entry_type=dr.DeviceEntryType.SERVICE,
    )

    coordinators: dict[str, DeviceCoordinator] = {}
    for slug, conf in _devices_conf(entry).items():
        # slug im conf sicherstellen (Storage-Key + Properties brauchen ihn)
        conf = {**conf, "slug": slug}
        coordinator = DeviceCoordinator(hass, entry, conf)
        await coordinator.async_load_stored()
        await coordinator.async_config_entry_first_refresh()
        coordinator.async_start_listeners()
        coordinators[slug] = coordinator

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["coordinators"] = coordinators

    def _stop_all() -> None:
        for c in coordinators.values():
            c.async_stop_listeners()

    entry.async_on_unload(_stop_all)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    coordinators: dict[str, DeviceCoordinator] = (
        bucket.pop("coordinators", {}) if bucket else {}
    )
    for c in coordinators.values():
        c.async_stop_listeners()
    return True
