"""Modul: Title Classifier.

Status: READY. Voll lauffähig unter der Toolbox-Domain `bennis_toolbox`.

- unique_id-Präfix:  `bennis_toolbox_title_classifier_*`
- Services:          `bennis_toolbox.title_classifier_*`
- WebSocket:         `bennis_toolbox/title_classifier/*`
- Storage:           `.storage/bennis_toolbox_title_classifier_entries_<entry_id>`
- Panel-URL:         `/bennis_toolbox_title_classifier`
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .entities import async_get_entities  # re-export
from .flow import ConfigFlowHelper, OptionsFlowHelper  # re-export
from .panel import async_register_panel  # re-export
from .runtime import WatcherRuntime
from .services_impl import SERVICES  # re-export
from .websockets_impl import WEBSOCKETS  # re-export

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
    runtime = WatcherRuntime(hass, entry)
    await runtime.async_setup()
    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["runtime"] = runtime
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    runtime = bucket.pop("runtime", None) if bucket else None
    if runtime is not None:
        await runtime.async_unload()
    return True
