"""Toolbox-weite Konstanten.

Es gibt genau eine HA-Integrationsdomäne: `bennis_toolbox`. Alles, was nach
außen sichtbar wird (Storage-Keys, Service-Namen, WebSocket-Befehle, Panel-
URLs), ist innerhalb dieser Domäne mit der Modul-ID präfixiert.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final[str] = "bennis_toolbox"

# Datenwurzel in hass.data[DOMAIN]:
#   {
#       "entries": { entry_id: <ModuleRuntime> },
#       "services_registered": bool,
#   }
DATA_ENTRIES: Final[str] = "entries"
DATA_SERVICES_REGISTERED: Final[str] = "services_registered"

# Marker im ConfigEntry.data
CONF_MODULE_ID: Final[str] = "_module_id"

# Storage-Präfix: jede Modul-Komponente benutzt
#   Store(hass, STORAGE_VERSION, storage_key("wake_planner", "plans"))
# damit Dateien unter .storage/bennis_toolbox_<module>_<name> landen.
STORAGE_PREFIX: Final[str] = f"{DOMAIN}_"


def storage_key(module_id: str, suffix: str) -> str:
    """Stabiler Storage-Key innerhalb der Toolbox."""
    return f"{STORAGE_PREFIX}{module_id}_{suffix}"


def service_name(module_id: str, action: str) -> str:
    """Service heißt z.B. `bennis_toolbox.wake_planner_set_plan`."""
    return f"{module_id}_{action}"


def websocket_type(module_id: str, command: str) -> str:
    """WebSocket-Befehl heißt z.B. `bennis_toolbox/wake_planner/list`."""
    return f"{DOMAIN}/{module_id}/{command}"


def panel_url_path(module_id: str) -> str:
    """Sidebar-URL-Path eines Modul-Panels: `bennis_toolbox_wake_planner`."""
    return f"{DOMAIN}_{module_id}"


def unique_id(module_id: str, *parts: str) -> str:
    """Eindeutige unique_id mit Modul-Präfix."""
    return "_".join((DOMAIN, module_id, *parts))
