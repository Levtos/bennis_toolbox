"""Frontend-Panel des Wake-Planner-Moduls.

Static-Path und Sidebar-Panel werden unter dem Toolbox-Präfix registriert:
- statische Dateien:  /bennis_toolbox_wake_planner/frontend/
- Sidebar-URL-Path:   bennis_toolbox_wake_planner
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

from ...const import panel_url_path
from .const import MODULE_ID

_URL_PATH = panel_url_path(MODULE_ID)  # bennis_toolbox_wake_planner
_STATIC_PREFIX = f"/{_URL_PATH}/frontend"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Static path + Sidebar-Panel idempotent registrieren."""
    if _URL_PATH in hass.data.get("frontend_panels", {}):
        return
    frontend_dir = Path(__file__).parent / "frontend"
    if not frontend_dir.exists():
        return
    await hass.http.async_register_static_paths([
        frontend.StaticPathConfig(_STATIC_PREFIX, str(frontend_dir), cache_headers=False)
    ])
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
