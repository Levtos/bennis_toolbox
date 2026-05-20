"""Modul: Benni Media Context.

Status: READY. Liefert media-/player-/quiet-/entertainment-Kontext unter der
einen HA-Domain `bennis_toolbox`. Title Classifier wird **nicht** importiert,
sondern als HA-Entity-Output konsumiert (Felder `classifier_ps5`, `classifier_pc`,
`classifier_homepods`, `classifier_media`).

- unique_id-Präfix: `bennis_toolbox_benni_media_context_*`
- Services:         `bennis_toolbox.benni_media_context_*`
- Events:           `bennis_toolbox_benni_media_context_{start_radio,stop_media}`
- Keine WebSocket-Befehle, kein Panel, kein Storage.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .coordinator import BenniMediaCoordinator
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
    coord = BenniMediaCoordinator(hass, entry)
    await coord.async_setup()

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["coordinator"] = coord
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    coord: BenniMediaCoordinator | None = bucket.pop("coordinator", None) if bucket else None
    if coord is not None:
        await coord.async_unload()
    return True
