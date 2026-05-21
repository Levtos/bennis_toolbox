"""Modul: Wake Planner.

Status: READY. Voll lauffähig unter der Toolbox-Domain `bennis_toolbox`.

- unique_id-Präfix:  `bennis_toolbox_wake_planner_*`
- Services:          `bennis_toolbox.wake_planner_*`
- WebSocket:         `bennis_toolbox/wake_planner/*`
- Storage:           `.storage/bennis_toolbox_wake_planner_state_<entry_id>`
- Panel-URL:         `/bennis_toolbox_wake_planner`
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, callback

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC  # SPEC ist HA-frei deklariert
from .coordinator import WakePlannerCoordinator
from .entities import async_get_entities  # re-export für Platform-Dispatcher
from .flow import ConfigFlowHelper, OptionsFlowHelper  # re-export für Umbrella-Flow
from .panel import async_register_panel    # re-export für Umbrella-Setup
from .services_impl import SERVICES        # re-export für Service-Dispatcher
from .websockets_impl import WEBSOCKETS    # re-export für WS-Dispatcher

_LOGGER = logging.getLogger(__name__)


__all__ = [
    "SPEC",
    "SERVICES",
    "WEBSOCKETS",
    "ConfigFlowHelper",
    "OptionsFlowHelper",
    "async_setup_entry",
    "async_unload_entry",
    "async_get_entities",
    "async_register_panel",
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = WakePlannerCoordinator(hass, entry)
    await coordinator.async_load()

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["coordinator"] = coordinator
    if hass.is_running:
        await coordinator.async_config_entry_first_refresh()
    else:
        @callback
        def _async_refresh_after_started(_event) -> None:
            hass.async_create_task(coordinator.async_config_entry_first_refresh())

        bucket["wake_planner_startup_unsub"] = hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED,
            _async_refresh_after_started,
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    if bucket:
        unsub = bucket.pop("wake_planner_startup_unsub", None)
        if unsub:
            unsub()
        bucket.pop("coordinator", None)
    return True
