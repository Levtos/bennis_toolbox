"""Benni's Toolbox — Umbrella-Integration.

Eine HA-Domain, viele Module. Ein Config-Entry pro aktivierter Modulinstanz;
die Modul-ID steckt in `entry.data[CONF_MODULE_ID]`. Das Umbrella-`__init__`
dispatcht setup/unload an das jeweilige Modul, registriert auf
`async_setup` einmalig alle Modul-Services/WebSocket-Befehle und kümmert
sich um Panel-Hooks.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from . import services as svc_dispatcher
from . import websocket_api as ws_dispatcher
from .const import (
    CONF_MODULE_ID,
    DATA_ENTRIES,
    DATA_SERVICES_REGISTERED,
    DOMAIN,
)
from .modules import REGISTERED_MODULE_IDS, get_spec, load_module
from .modules.base import ModuleStatus

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Wird genau einmal pro HA-Start aufgerufen — registriert Services/WS."""
    hass.data.setdefault(DOMAIN, {DATA_ENTRIES: {}, DATA_SERVICES_REGISTERED: False})
    if not hass.data[DOMAIN][DATA_SERVICES_REGISTERED]:
        await svc_dispatcher.async_register_all(hass)
        ws_dispatcher.async_register_all(hass)
        hass.data[DOMAIN][DATA_SERVICES_REGISTERED] = True
        _LOGGER.debug("toolbox services + websockets registered")
    # Panels werden lazy registriert, wenn ein Modul mit `has_panel=True`
    # tatsächlich einen Entry hat — siehe async_setup_entry.
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup pro Modul-Instanz."""
    module_id: str | None = entry.data.get(CONF_MODULE_ID)
    if not module_id:
        _LOGGER.error("entry %s has no %s — refusing to set up", entry.entry_id, CONF_MODULE_ID)
        return False
    if module_id not in REGISTERED_MODULE_IDS:
        _LOGGER.error("entry %s references unknown module %r", entry.entry_id, module_id)
        return False

    spec = get_spec(module_id)
    if spec.status in (ModuleStatus.STUB, ModuleStatus.PENDING):
        _LOGGER.warning(
            "module %s is %s — entry %s will load as no-op",
            module_id, spec.status.value, entry.entry_id,
        )
        hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id] = {"module_id": module_id, "status": spec.status.value}
        return True

    mod = load_module(module_id)
    setup = getattr(mod, "async_setup_entry", None)
    if setup is None:
        _LOGGER.error("module %s exposes no async_setup_entry", module_id)
        return False

    ok = await setup(hass, entry)
    if not ok:
        return False

    if spec.platforms:
        await hass.config_entries.async_forward_entry_setups(entry, list(spec.platforms))

    if spec.has_panel:
        panel_reg = getattr(mod, "async_register_panel", None)
        if panel_reg:
            try:
                await panel_reg(hass)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("module %s panel registration failed: %s", module_id, err)

    hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id] = {"module_id": module_id, "status": "ready"}
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    module_id: str | None = entry.data.get(CONF_MODULE_ID)
    state: dict[str, Any] = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).pop(entry.entry_id, {})
    if not module_id or state.get("status") != "ready":
        return True

    spec = get_spec(module_id)
    if spec.platforms:
        await hass.config_entries.async_unload_platforms(entry, list(spec.platforms))
    mod = load_module(module_id)
    unload = getattr(mod, "async_unload_entry", None)
    if unload:
        try:
            await unload(hass, entry)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("module %s unload raised: %s", module_id, err)
    return True


async def _async_reload_on_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
