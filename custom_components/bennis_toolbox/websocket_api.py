"""WebSocket-Dispatcher der Toolbox.

Module exportieren optional `WEBSOCKETS`:

    WEBSOCKETS: list[Callable] = [ws_list, ws_set_enum, ...]

Jeder Eintrag ist eine Funktion, die schon mit `@websocket_api.websocket_command`
dekoriert ist. Der Toolbox-Wrapper sorgt dafür, dass `type` der Konvention
`bennis_toolbox/<module>/<command>` folgt (das Modul deklariert dies selbst,
die Toolbox prüft nur).
"""

from __future__ import annotations

import logging
from typing import Callable

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .modules import REGISTERED_MODULE_IDS, load_module

_LOGGER = logging.getLogger(__name__)


async def async_register_all(hass: HomeAssistant) -> None:
    for module_id in REGISTERED_MODULE_IDS:
        try:
            mod = await hass.async_add_executor_job(load_module, module_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("skip websockets for %s: %s", module_id, err)
            continue
        for ws in getattr(mod, "WEBSOCKETS", []) or []:
            try:
                websocket_api.async_register_command(hass, ws)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "module %s: failed to register WS command %r: %s",
                    module_id, getattr(ws, "__name__", ws), err,
                )
