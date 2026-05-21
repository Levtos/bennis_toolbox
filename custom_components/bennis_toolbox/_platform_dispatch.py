"""Gemeinsame Logik aller Platform-Dispatcher.

Jede `<platform>.py` direkt unter `bennis_toolbox/` ruft hier durch. Damit
HA die Plattform findet, MUSS die Datei am Integrations-Root liegen
(z.B. `bennis_toolbox/sensor.py`).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODULE_ID
from .modules import load_module

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform_for(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    platform: Platform,
) -> None:
    module_id = entry.data.get(CONF_MODULE_ID)
    if not module_id:
        _LOGGER.error("entry %s missing %s", entry.entry_id, CONF_MODULE_ID)
        return
    try:
        mod = await hass.async_add_executor_job(load_module, module_id)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("cannot load module %s: %s", module_id, err)
        return
    getter = getattr(mod, "async_get_entities", None)
    if getter is None:
        return
    entities: list[Any] = await getter(hass, entry, platform)
    if entities:
        async_add_entities(entities)
