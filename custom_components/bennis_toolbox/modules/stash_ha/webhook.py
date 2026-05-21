"""Webhook view für Stash → Home Assistant.

URL: `/api/bennis_toolbox/stash_ha/webhook/<entry_id>`.

Stash kann nach jedem `sceneSaveActivity` einen POST schicken; wir lösen
darauf einen sofortigen Coordinator-Refresh aus.
"""
from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from ...const import DATA_ENTRIES, DOMAIN
from .const import MODULE_ID

_LOGGER = logging.getLogger(__name__)


def webhook_url(entry_id: str) -> str:
    return f"/api/{DOMAIN}/{MODULE_ID}/webhook/{entry_id}"


class StashWebhookView(HomeAssistantView):
    """Triggert sofortiges Refresh des Playback-Coordinators."""

    requires_auth = False

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.url = webhook_url(entry_id)
        self.name = f"api:{DOMAIN}:{MODULE_ID}:webhook:{entry_id}"

    async def post(self, request: web.Request) -> web.Response:
        try:
            await request.json(content_type=None)
        except Exception:  # noqa: BLE001
            pass
        bucket = self.hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(self.entry_id)
        runtime = bucket.get("runtime") if bucket else None
        if runtime:
            coord = runtime.get("playback")
            if coord:
                self.hass.async_create_task(coord.async_request_refresh())
        return self.json({"ok": True})
