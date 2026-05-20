"""Frontend-Panel-Registrierung für Title Classifier.

Sidebar-URL-Path / Static-Path / Custom-Element folgen dem Toolbox-Schema:
- Sidebar:        /bennis_toolbox_title_classifier
- Static path:    /bennis_toolbox_title_classifier/frontend
- Panel JS-URL:   /bennis_toolbox_title_classifier/frontend/title-classifier-panel.js
- Custom-Element: title-classifier-panel
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from ...const import panel_url_path
from .const import MODULE_ID, PANEL_ICON, PANEL_TITLE

_URL_PATH = panel_url_path(MODULE_ID)  # bennis_toolbox_title_classifier
_STATIC_PREFIX = f"/{_URL_PATH}/frontend"


async def async_register_panel(hass: HomeAssistant) -> None:
    if _URL_PATH in hass.data.get("frontend_panels", {}):
        return
    frontend_dir = Path(__file__).parent / "frontend"
    if not frontend_dir.exists():
        return
    await hass.http.async_register_static_paths([
        StaticPathConfig(_STATIC_PREFIX, str(frontend_dir), cache_headers=False)
    ])
    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=_URL_PATH,
        require_admin=True,
        config={
            "_panel_custom": {
                "name": "title-classifier-panel",
                "embed_iframe": False,
                "trust_external": False,
                "js_url": f"{_STATIC_PREFIX}/title-classifier-panel.js",
            }
        },
    )
