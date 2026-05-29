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
from homeassistant.helpers import entity_registry as er

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .const import (
    CONF_DEVICES,
    DEVICE_OBJECT_ID_PREFIX,
    GROUP_OBJECT_ID_PREFIX,
    MODULE_ID,
    NAME,
)
from .coordinator import DeviceCoordinator
from .entities import async_get_entities  # re-export
from .flow import ConfigFlowHelper, OptionsFlowHelper  # re-export
from .services_impl import SERVICES  # re-export

_LOGGER = logging.getLogger(__name__)

# Stabile Identifier des Hub-Geräts (alle Geräte hängen via_device daran).
HUB_IDENTIFIER = (DOMAIN, f"{MODULE_ID}_hub")
# Eigener Hub für Atomic Light Groups — Gruppen erscheinen als eigene
# Geräte-Kategorie, getrennt von den Einzelgeräten.
GROUPS_HUB_IDENTIFIER = (DOMAIN, f"{MODULE_ID}_groups_hub")

__all__ = [
    "SPEC",
    "SERVICES",
    "ConfigFlowHelper",
    "OptionsFlowHelper",
    "HUB_IDENTIFIER",
    "GROUPS_HUB_IDENTIFIER",
    "async_setup_entry",
    "async_unload_entry",
    "async_get_entities",
]


def _devices_conf(entry: ConfigEntry) -> dict[str, dict[str, Any]]:
    raw = entry.options.get(CONF_DEVICES)
    return dict(raw) if isinstance(raw, dict) else {}


def _device_identifier(slug: str) -> tuple[str, str]:
    return (DOMAIN, f"{MODULE_ID}:{slug}")


def _reconcile_devices(
    hass: HomeAssistant, entry: ConfigEntry, devices_conf: dict[str, dict[str, Any]]
) -> None:
    """Entfernt verwaiste HA-Geräte (+ kaskadierend deren Entitäten) für
    Slugs, die nicht mehr in der Config stehen.

    HA räumt Sub-Geräte eines Config-Entries nicht selbst auf — beim
    'Gerät entfernen' (Options-Flow) bliebe sonst das HA-Device + die Entität
    als Waise bestehen. Läuft bei jedem Setup/Reload.
    """
    dev_reg = dr.async_get(hass)
    valid = {HUB_IDENTIFIER, GROUPS_HUB_IDENTIFIER} | {
        _device_identifier(slug) for slug in devices_conf
    }
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if not (set(device.identifiers) & valid):
            dev_reg.async_remove_device(device.id)

    # Stale-benannte Entitäten aufräumen: alles was nicht dem aktuellen
    # `benni_device_<slug>`-Schema folgt (z.B. Alt-Eintrag `sensor.tv`).
    # Der Registry-Eintrag wird entfernt; die Plattform legt die Entität
    # danach mit der korrekten, erzwungenen entity_id neu an.
    ent_reg = er.async_get(hass)
    valid_prefixes = (DEVICE_OBJECT_ID_PREFIX, GROUP_OBJECT_ID_PREFIX)
    for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        object_id = e.entity_id.split(".", 1)[1]
        if not object_id.startswith(valid_prefixes):
            ent_reg.async_remove(e.entity_id)


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
    # Eigener Hub für Atomic Light Groups — Gruppen erscheinen als eigene
    # Kategorie, nicht vermischt mit den Einzelgeräten.
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={GROUPS_HUB_IDENTIFIER},
        name=f"{NAME} · Light Groups",
        manufacturer="Benni's Toolbox",
        model="Light Groups Hub",
        entry_type=dr.DeviceEntryType.SERVICE,
    )

    devices_conf = _devices_conf(entry)
    _reconcile_devices(hass, entry, devices_conf)

    coordinators: dict[str, DeviceCoordinator] = {}
    for slug, conf in devices_conf.items():
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
