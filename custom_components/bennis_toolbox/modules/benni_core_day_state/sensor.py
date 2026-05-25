"""SensorEntity für Benni Core · Day State.

Genau eine Entity:
- Object-ID: `benni_core_day_state` (gemäß naming.md aus dem LH)
- State: aktuelle Detailphase (slug, eine von 8 — LH §4.1)
- device_class: enum
- Attribute: vollständige Liste aus LH §13 (Pflicht + Debug)
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import DOMAIN, unique_id
from .const import (
    DETAIL_PHASE_SLUGS,
    SOLAR_NOON_SOURCE_FALLBACK_LABEL,
    DetailPhase,
)
from .coordinator import DayStateCoordinator, coordinator_from_hass
from .logic import DayStateResult

MODULE_ID = "benni_core_day_state"
OBJECT_ID = "benni_core_day_state"  # → sensor.benni_core_day_state


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: str
) -> list[Entity]:
    """Vom Toolbox-Platform-Dispatcher aufgerufen."""
    if platform != Platform.SENSOR:
        return []
    coordinator = coordinator_from_hass(hass, entry)
    if coordinator is None:
        return []
    return [DayStateSensor(coordinator, entry)]


class DayStateSensor(CoordinatorEntity[DayStateCoordinator], SensorEntity):
    """Der eine Sensor des Moduls."""

    _attr_has_entity_name = False  # Voller Name, kein Device-Namespacing
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(DETAIL_PHASE_SLUGS)
    _attr_icon = "mdi:weather-sunset"
    _attr_translation_key = "day_state"
    _attr_name = "Benni Core Day State"

    def __init__(
        self, coordinator: DayStateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, "state")
        self._attr_suggested_object_id = OBJECT_ID

    # ─────────────────────────────────────────────────────── State

    @property
    def native_value(self) -> str | None:
        result: DayStateResult | None = self.coordinator.data
        if result is None:
            # Sollte laut LH §4.4 nie unknown/unavailable sein — aber während
            # des allerersten Refresh-Fensters kann es das doch sein.
            return None
        return result.detail_phase.slug

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Alle Pflicht- und Debug-Attribute laut LH §13."""
        result: DayStateResult | None = self.coordinator.data
        if result is None:
            return {}

        # Solar-Noon-Source-Label (LH §13.1: "Fachliche Quelle des Solar-Noon-Werts")
        solar_noon_source_label = (
            self.coordinator.solar_noon_source
            if not result.solar_noon_fallback_active
            else SOLAR_NOON_SOURCE_FALLBACK_LABEL
        )

        attrs: dict[str, Any] = {
            # Pflicht (LH §13.1)
            "detail_phase": result.detail_phase.slug,
            "detail_phase_id": result.detail_phase.value,
            "master_phase": result.master_phase.slug,
            "master_phase_id": result.master_phase.value,
            "detail_phase_options": list(DETAIL_PHASE_SLUGS),
            "master_phase_options": [
                "morning",
                "midday",
                "evening",
                "night",
            ],
            "phase_starts": result.phase_starts,
            "master_phase_starts": result.master_phase_starts,
            "current_phase_started_at": result.current_phase_started_at,
            "next_phase": result.next_phase.slug,
            "next_phase_at": result.next_phase_at,
            "minutes_until_next_phase": result.minutes_until_next_phase,
            "next_master_phase": (
                result.next_master_phase.slug
                if result.next_master_phase is not None
                else None
            ),
            "next_master_phase_at": result.next_master_phase_at,
            "solar_noon_at": result.solar_noon_at,
            "solar_noon_source": solar_noon_source_label,
            "solar_noon_fallback_active": result.solar_noon_fallback_active,
            "seasonal_factor": result.seasonal_factor,
            "seasonal_offset_minutes": result.seasonal_offset_minutes,
            # Debug (LH §13.2)
            "morning_fix_at": result.morning_fix_at,
            "night_fix_at": result.night_fix_at,
            "midday_start_at": result.midday_start_at,
            "evening_start_at": result.evening_start_at,
            "late_morning_start_at": result.late_morning_start_at,
            "late_evening_start_at": result.late_evening_start_at,
            "late_night_start_at": result.late_night_start_at,
            "month_morning_split": result.month_morning_split,
            "month_evening_split": result.month_evening_split,
        }
        return attrs
