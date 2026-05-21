"""Diagnostics-Dump pro Toolbox-Entry."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, DATA_ENTRIES
from .modules import all_specs
from .modules.base import platform_value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    entries_state = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {})
    return {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "module_id": entry.data.get("_module_id"),
            "options": dict(entry.options),
            "state": entries_state.get(entry.entry_id, {}),
        },
        "all_modules": [
            {
                "module_id": s.module_id,
                "name": s.name,
                "status": s.status.value,
                "platforms": [platform_value(p) for p in s.platforms],
                "has_panel": s.has_panel,
                "has_websocket": s.has_websocket,
                "has_services": s.has_services,
            }
            for s in await hass.async_add_executor_job(all_specs)
        ],
    }
