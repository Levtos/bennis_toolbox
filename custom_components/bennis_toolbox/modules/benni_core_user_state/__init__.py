"""Modul: Benni Core · User State.

Status: PENDING (Skelett — wird Schritt für Schritt auf READY gehoben).

Zweites der drei "Herzen" der neuen benni_core-Architektur. Liefert
`sensor.benni_core_user_bio_state` (sleep/waking/awake) plus Sleep-/
Wake-Timestamps und abgeleitete Dauern, nach Lastenheft Context State
v1.1 §4.1 und R-US-01..R-US-07.

Persistenter Bio-State über HA-Restarts (R-US-05) via Toolbox-Storage-
Helper. Wake-Trigger (R-US-06, R-US-07) konsumieren `master_phase`
aus Day State und greifen nur tagsüber (morning/midday/evening).

- unique_id-Präfix:  `bennis_toolbox_benni_core_user_state_*`
- Services:          `bennis_toolbox.benni_core_user_state_*` (set_sleep, set_waking, set_awake)
- Storage:           `.storage/bennis_toolbox_benni_core_user_state_state_<entry_id>`
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .coordinator import UserStateCoordinator
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
    coordinator = UserStateCoordinator(hass, entry)
    await coordinator.async_load_stored()
    await coordinator.async_config_entry_first_refresh()

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["coordinator"] = coordinator

    coordinator.async_start_listeners()
    entry.async_on_unload(coordinator.async_stop_listeners)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    coordinator: UserStateCoordinator | None = (
        bucket.pop("coordinator", None) if bucket else None
    )
    if coordinator is not None:
        coordinator.async_stop_listeners()
    return True
