"""Wake Planner integration."""

from __future__ import annotations

from pathlib import Path
import logging

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    SERVICE_ADD_PERSON,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_REMOVE_PERSON,
    SERVICE_SET_OVERRIDE,
    SERVICE_SET_RULES,
    SERVICE_SET_SPECIAL_RULES,
    SERVICE_SKIP_NEXT,
)
from .coordinator import WakePlannerCoordinator
from .services import async_setup_services
from .websocket_api import async_register_websocket_api

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]
_SERVICES = (
    SERVICE_SKIP_NEXT,
    SERVICE_SET_OVERRIDE,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_ADD_PERSON,
    SERVICE_REMOVE_PERSON,
    SERVICE_SET_RULES,
    SERVICE_SET_SPECIAL_RULES,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    coordinator = WakePlannerCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_setup_services(hass)
    async_register_websocket_api(hass)
    await _async_register_panel(hass)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            for service in _SERVICES:
                hass.services.async_remove(DOMAIN, service)
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coordinator: WakePlannerCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        await coordinator.async_request_refresh()


async def _async_register_panel(hass: HomeAssistant) -> None:
    if "wake-planner" in hass.data.get("frontend_panels", {}):
        return
    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths([
        frontend.StaticPathConfig("/wake_planner/frontend", str(frontend_dir), cache_headers=False)
    ])
    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="Wake Planner",
        sidebar_icon="mdi:alarm-check",
        frontend_url_path="wake-planner",
        require_admin=False,
        config={
            "_panel_custom": {
                "name": "wake-planner-panel",
                "embed_iframe": False,
                "trust_external": False,
                "js_url": "/wake_planner/frontend/wake-planner-panel.js",
            }
        },
    )
