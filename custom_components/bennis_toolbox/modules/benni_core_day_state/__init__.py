"""Modul: Benni Core · Day State.

Status: PENDING (Skelett — wird Schritt für Schritt auf READY gehoben).

Erstes der drei "Herzen" der neuen benni_core-Architektur. Liefert einen
einzigen Sensor `sensor.benni_core_day_state` mit der aktuellen Detailphase
als State und allen Übergangszeiten als Attribute. Lastenheft:
`einhornzentrale/docs/lastenhefte/reviewed/day_state/lastenheft.md` (v1.1).

- unique_id-Präfix:  `bennis_toolbox_benni_core_day_state_*`
- Keine Services, keine WebSockets, kein Panel.
- Einzige externe Eingabe: Solar-Noon-Quelle (Config Flow).
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import DATA_ENTRIES, DOMAIN
from ._spec import SPEC
from .coordinator import DayStateCoordinator
from .entities import async_get_entities  # re-export
from .flow import ConfigFlowHelper, OptionsFlowHelper  # re-export

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "SPEC",
    "ConfigFlowHelper",
    "OptionsFlowHelper",
    "async_setup_entry",
    "async_unload_entry",
    "async_get_entities",
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Coordinator anlegen und Listener starten.

    Solange SPEC.status == PENDING ist, wird die Modul-Runtime von der
    Toolbox-Registry als no-op behandelt — dieses Setup wird also erst nach
    Statuswechsel auf READY tatsächlich aufgerufen.
    """
    coordinator = DayStateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    bucket = hass.data[DOMAIN][DATA_ENTRIES].setdefault(entry.entry_id, {})
    bucket["coordinator"] = coordinator

    coordinator.async_start_listeners()
    entry.async_on_unload(coordinator.async_stop_listeners)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    coordinator: DayStateCoordinator | None = (
        bucket.pop("coordinator", None) if bucket else None
    )
    if coordinator is not None:
        coordinator.async_stop_listeners()
    return True
