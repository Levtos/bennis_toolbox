"""Frontend-Panel des Wake-Planner-Moduls.

Static-Path und Sidebar-Panel werden unter dem Toolbox-Präfix registriert:
- statische Dateien:  /bennis_toolbox_wake_planner/frontend/
- Sidebar-URL-Path:   bennis_toolbox_wake_planner
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

from ...const import panel_url_path
from .const import MODULE_ID

_LOGGER = logging.getLogger(__name__)

_URL_PATH = panel_url_path(MODULE_ID)  # bennis_toolbox_wake_planner
_STATIC_PREFIX = f"/{_URL_PATH}/frontend"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Static path + Sidebar-Panel idempotent registrieren.

    Reloads of the integration leave the panel + static path
    registered. Re-registering either is what triggered the noisy
    "Overwriting panel …" warning. We swallow the duplicate-static-
    path error and remove a stale panel before re-registering so the
    title/icon stay in sync with the current code.
    """
    frontend_dir = Path(__file__).parent / "frontend"
    if not frontend_dir.exists():
        return
    try:
        await hass.http.async_register_static_paths([
            frontend.StaticPathConfig(_STATIC_PREFIX, str(frontend_dir), cache_headers=False)
        ])
    except (RuntimeError, ValueError) as err:
        _LOGGER.debug(
            "wake_planner static path already registered, skipping: %s", err
        )
    panels = hass.data.get("frontend_panels") or {}
    if _URL_PATH in panels:
        try:
            frontend.async_remove_panel(hass, _URL_PATH)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("wake_planner panel already absent during cleanup")
    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="Wake Planner",
        sidebar_icon="mdi:alarm-check",
        frontend_url_path=_URL_PATH,
        require_admin=False,
        config={
            "_panel_custom": {
                "name": "wake-planner-panel",
                "embed_iframe": False,
                "trust_external": False,
                "js_url": f"{_STATIC_PREFIX}/wake-planner-panel.js",
            }
        },
    )
