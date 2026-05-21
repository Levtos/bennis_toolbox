"""Modul: Stash HA.

Status: READY. Stash-Mediaplayer-Bridge unter der einen HA-Domain
`bennis_toolbox`. Keine Cross-Modul-Imports.

- unique_id-Präfix: `bennis_toolbox_stash_ha_*`
- Services:         `bennis_toolbox.stash_ha_*`
- Webhook-URL:      `/api/bennis_toolbox/stash_ha/webhook/<entry_id>`
- Kein eigener Storage; Coordinator hält State in memory.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .client import StashClient
from .const import (
    CONF_API_KEY,
    CONF_POLL_INTERVAL,
    CONF_URL,
    CONF_USE_WEBHOOK,
    DEFAULT_POLL_INTERVAL,
)
from .coordinator import StashLibraryCoordinator, StashPlaybackCoordinator
from .entities import async_get_entities  # re-export
from .flow import ConfigFlowHelper, OptionsFlowHelper  # re-export
from .services_impl import SERVICES  # re-export
from .webhook import StashWebhookView

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
    session = async_get_clientsession(hass)
    graphql_url: str = entry.data[CONF_URL]
    api_key: str = entry.data.get(CONF_API_KEY, "") or ""

    client = StashClient(graphql_url, session, api_key)
    poll_interval = int(entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))
    playback = StashPlaybackCoordinator(hass, client, entry, poll_interval)
    library = StashLibraryCoordinator(hass, client, entry)

    try:
        await playback.async_config_entry_first_refresh()
        await library.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(str(err)) from err

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    runtime = {
        "client": client,
        "playback": playback,
        "library": library,
    }
    bucket["runtime"] = runtime

    if entry.options.get(CONF_USE_WEBHOOK, False):
        view = StashWebhookView(hass, entry.entry_id)
        hass.http.register_view(view)
        runtime["webhook_view"] = view

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    _LOGGER.info("Stash HA connected to %s", graphql_url)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change so poll_interval / webhook take effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    if bucket:
        bucket.pop("runtime", None)
    return True
