"""Modul: Notification Router.

Status: READY. Routet Notifications kontextabhängig unter der einen HA-Domain
`bennis_toolbox`. Inputs (Bio/Activity/Presence/Headset/Quiet/Media/…) kommen
ausschließlich als HA-Entity-IDs aus dem Config-Flow — kein Python-Cross-
Modul-Import.

- unique_id-Präfix: `bennis_toolbox_notification_router_*`
- Services:         `bennis_toolbox.notification_router_*`
- Event:            `bennis_toolbox_notification_router_routed`
- Storage:          `.storage/bennis_toolbox_notification_router_state_<entry_id>`
- Keine WebSocket-Befehle, kein Panel.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .coordinator import NotificationRouter
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


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Push fresh options into a running router without rebuilding it."""
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    router: NotificationRouter | None = bucket.get("router") if bucket else None
    if router is not None:
        router.update_options(dict(entry.options))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    router = NotificationRouter(
        hass, entry.entry_id, dict(entry.data), dict(entry.options)
    )
    await router.async_load()

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["router"] = router

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    if bucket:
        bucket.pop("router", None)
    return True
