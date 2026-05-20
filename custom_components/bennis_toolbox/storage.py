"""Storage-Helper für Module.

Convenience-Wrapper, damit Module nicht selbst die Toolbox-Domain in den
Storage-Key kleben müssen. Konvention:

    .storage/bennis_toolbox_<module_id>_<suffix>
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import storage_key

DEFAULT_VERSION = 1


def make_store(
    hass: HomeAssistant,
    module_id: str,
    suffix: str,
    *,
    version: int = DEFAULT_VERSION,
) -> Store[dict[str, Any]]:
    return Store(hass, version, storage_key(module_id, suffix))
