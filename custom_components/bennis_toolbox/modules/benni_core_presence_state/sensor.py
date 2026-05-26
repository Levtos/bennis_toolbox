"""SensorEntities für Benni Core · Presence State (LH §3.2)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import unique_id
from .const import (
    BAND_OPTIONS,
    DIRECTION_OPTIONS,
    MODULE_ID,
    PRESENCE_HOUSEHOLD_OPTIONS,
    PRESENCE_PERSONAL_OPTIONS,
    TRANSITION_OPTIONS,
)
from .coordinator import PresenceComputed, PresenceStateCoordinator, coordinator_from_hass


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: str
) -> list[Entity]:
    coordinator = coordinator_from_hass(hass, entry)
    if coordinator is None:
        return []
    if platform == Platform.SENSOR:
        return [
            PersonalSensor(coordinator, entry),
            HouseholdSensor(coordinator, entry),
            TransitionSensor(coordinator, entry),
            BandSensor(coordinator, entry),
            DirectionSensor(coordinator, entry),
            DistanceSensor(coordinator, entry),
            PreheatSourceSensor(coordinator, entry),
        ]
    if platform == Platform.BINARY_SENSOR:
        return [PreheatActiveBinarySensor(coordinator, entry)]
    return []


class _Base(CoordinatorEntity[PresenceStateCoordinator]):
    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: PresenceStateCoordinator,
        entry: ConfigEntry,
        *,
        suffix: str,
        object_id: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, suffix)
        self._attr_suggested_object_id = object_id
        self._attr_name = name

    @property
    def _result(self) -> PresenceComputed | None:
        return self.coordinator.data

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self._result
        if r is None:
            return {}
        return {
            "home_candidate": r.home_candidate,
            "home_candidate_reason": r.home_candidate_reason,
            "home_gate": r.home_gate,
            "bei_eltern": r.bei_eltern,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Sensors
# ─────────────────────────────────────────────────────────────────────────────


class PersonalSensor(_Base, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(PRESENCE_PERSONAL_OPTIONS)
    _attr_icon = "mdi:account-check"

    def __init__(self, coordinator, entry):
        super().__init__(
            coordinator,
            entry,
            suffix="personal",
            object_id="benni_core_presence_personal",
            name="Benni Core Presence Personal",
        )

    @property
    def native_value(self) -> str | None:
        r = self._result
        return r.personal.value if r else None


class HouseholdSensor(_Base, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(PRESENCE_HOUSEHOLD_OPTIONS)
    _attr_icon = "mdi:home-account"

    def __init__(self, coordinator, entry):
        super().__init__(
            coordinator,
            entry,
            suffix="household",
            object_id="benni_core_presence_household",
            name="Benni Core Presence Household",
        )

    @property
    def native_value(self) -> str | None:
        r = self._result
        return r.household.value if r else None


class TransitionSensor(_Base, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(TRANSITION_OPTIONS)
    _attr_icon = "mdi:swap-horizontal"

    def __init__(self, coordinator, entry):
        super().__init__(
            coordinator,
            entry,
            suffix="transition",
            object_id="benni_core_presence_transition",
            name="Benni Core Presence Transition",
        )

    @property
    def native_value(self) -> str | None:
        r = self._result
        return r.transition.value if r else None


class BandSensor(_Base, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(BAND_OPTIONS)
    _attr_icon = "mdi:map-marker-radius"

    def __init__(self, coordinator, entry):
        super().__init__(
            coordinator,
            entry,
            suffix="band",
            object_id="benni_core_presence_band",
            name="Benni Core Presence Band",
        )

    @property
    def native_value(self) -> str | None:
        r = self._result
        return r.band.value if r else None


class DirectionSensor(_Base, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(DIRECTION_OPTIONS)
    _attr_icon = "mdi:compass"

    def __init__(self, coordinator, entry):
        super().__init__(
            coordinator,
            entry,
            suffix="direction",
            object_id="benni_core_presence_direction",
            name="Benni Core Presence Direction",
        )

    @property
    def native_value(self) -> str | None:
        r = self._result
        return r.direction.value if r else None


class DistanceSensor(_Base, SensorEntity):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = "m"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-distance"

    def __init__(self, coordinator, entry):
        super().__init__(
            coordinator,
            entry,
            suffix="distance",
            object_id="benni_core_presence_distance",
            name="Benni Core Presence Distance",
        )

    @property
    def native_value(self) -> float | None:
        r = self._result
        return r.distance_m if r else None


class PreheatSourceSensor(_Base, SensorEntity):
    _attr_icon = "mdi:source-pull"

    def __init__(self, coordinator, entry):
        super().__init__(
            coordinator,
            entry,
            suffix="preheat_source",
            object_id="benni_core_presence_preheat_source",
            name="Benni Core Presence Preheat Source",
        )

    @property
    def native_value(self) -> str | None:
        r = self._result
        if r is None:
            return None
        return r.preheat_source or "none"


class PreheatActiveBinarySensor(_Base, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:home-thermometer"

    def __init__(self, coordinator, entry):
        super().__init__(
            coordinator,
            entry,
            suffix="preheat_active",
            object_id="benni_core_presence_preheat_active",
            name="Benni Core Presence Preheat Active",
        )

    @property
    def is_on(self) -> bool | None:
        r = self._result
        return r.preheat_active if r else None
