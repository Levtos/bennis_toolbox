"""DataUpdateCoordinator für Benni Core · Day State.

Trigger laut LH §5:
- R1: Minütlich (`update_interval=60s`)
- R2: Bei State-Change der konfigurierten Solar-Noon-Quelle

Compute lebt in `logic.py` als pure Funktion. Der Coordinator macht nur:
1. Solar Noon aus konfigurierter Source-Entity lesen (mit Source-spezifischer
   Normalisierung — `sun.sun.next_noon` braucht 24h-Korrektur).
2. `logic.compute_day_state(now, solar_noon)` aufrufen.
3. Ergebnis cachen, Entities updaten.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from ...const import DOMAIN
from . import logic
from .const import CONF_SOLAR_NOON_SOURCE, DEFAULT_SOLAR_NOON_SOURCE
from .logic import DayStateResult

_LOGGER = logging.getLogger(__name__)

MODULE_ID = "benni_core_day_state"
UPDATE_INTERVAL_SECONDS = 60


class DayStateCoordinator(DataUpdateCoordinator[DayStateResult]):
    """Treibt den einen Day-State-Sensor."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{MODULE_ID}_{entry.entry_id}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.entry = entry
        self._unsub_listeners: list[CALLBACK_TYPE] = []

    @property
    def solar_noon_source(self) -> str:
        """Konfigurierte Source-Entity (z.B. `sun.sun` oder `sensor.sun2_solar_noon`)."""
        return self.entry.options.get(
            CONF_SOLAR_NOON_SOURCE,
            self.entry.data.get(CONF_SOLAR_NOON_SOURCE, DEFAULT_SOLAR_NOON_SOURCE),
        )

    # ─────────────────────────────────────────────────────── Lifecycle

    def async_start_listeners(self) -> None:
        """State-Change-Listener für Solar-Noon-Quelle registrieren.

        Der minütliche Trigger läuft bereits über `update_interval` aus
        DataUpdateCoordinator.
        """
        self._unsub_listeners.append(
            async_track_state_change_event(
                self.hass,
                [self.solar_noon_source],
                self._async_on_solar_noon_change,
            )
        )

    def async_stop_listeners(self) -> None:
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    @callback
    def _async_on_solar_noon_change(self, event: Event) -> None:
        """Solar-Noon-Source hat sich geändert → sofortige Neuberechnung."""
        self.async_set_updated_data(self._compute())

    # ─────────────────────────────────────────────────────── Compute

    async def _async_update_data(self) -> DayStateResult:
        return self._compute()

    def _compute(self) -> DayStateResult:
        now = dt_util.now()
        solar_noon = self._read_solar_noon(now)
        return logic.compute_day_state(now, solar_noon)

    # ─────────────────────────────────────────────────────── Solar-Noon-Read

    def _read_solar_noon(self, now: datetime) -> datetime | None:
        """Lies Solar Noon aus der konfigurierten Source-Entity.

        Source-spezifische Normalisierung:
        - `sun.sun`: nutzt `next_noon`-Attribut (HA Core). Wenn der nächste
          Noon > 12h entfernt ist, war heutiges Noon bereits (= next_noon
          minus 1 Tag).
        - Alle anderen: State-Wert wird direkt als datetime geparst (so wie
          sun2 ihn ausgibt, oder ein eigener Template-Helper).
        Bei jedem Fehler oder unavailable: None zurückgeben → logic.py
        triggert dann den 12:46-Fallback.
        """
        source = self.solar_noon_source
        state = self.hass.states.get(source)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None

        if source == "sun.sun":
            next_noon_str = state.attributes.get("next_noon")
            if not next_noon_str:
                return None
            next_noon = dt_util.parse_datetime(next_noon_str)
            if next_noon is None:
                return None
            # Wenn `next_noon` > 12h entfernt ist, war heutiger Noon bereits
            # → den 24h zurück.
            if (next_noon - now) > timedelta(hours=12):
                return next_noon - timedelta(days=1)
            return next_noon

        parsed = dt_util.parse_datetime(state.state)
        return parsed  # Kann None sein, das ist ok — Fallback greift


@callback
def coordinator_from_hass(
    hass: HomeAssistant, entry: ConfigEntry
) -> DayStateCoordinator | None:
    """Hole den Coordinator für eine bestimmte Config Entry."""
    from ...const import DATA_ENTRIES

    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    if not bucket:
        return None
    return bucket.get("coordinator")
