"""Diagnostics für bennis_toolbox."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .status import collect_member_status


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    statuses = await collect_member_status(hass)
    return {
        "entry": {
            "title": entry.title,
            "options": dict(entry.options),
        },
        "members": [s.as_dict() for s in statuses],
    }
