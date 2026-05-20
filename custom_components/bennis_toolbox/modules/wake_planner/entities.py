"""Wake-Planner-Entities (Sensor + Binary Sensor).

Werden vom Umbrella-Platform-Dispatcher über `async_get_entities` angefragt.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from ...const import DOMAIN, unique_id
from .const import (
    CONF_HOLIDAY_BEHAVIOR,
    CONF_MANUAL_HOLIDAY_DATES,
    HOLIDAY_SKIP,
    MODULE_ID,
    PersonConfig,
    WakeState,
)
from .coordinator import WakePlannerCoordinator, coordinator_from_hass
from .util import rule_to_dict


SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key="wake_state", translation_key="wake_state"),
    SensorEntityDescription(
        key="next_wake",
        translation_key="next_wake",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)

BINARY_DESCRIPTION = BinarySensorEntityDescription(
    key="wake_needed",
    translation_key="wake_needed",
    device_class=BinarySensorDeviceClass.RUNNING,
)


def _device_info(entry: ConfigEntry, person: PersonConfig) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, f"{MODULE_ID}_{entry.entry_id}_{person.slug}")},
        "name": f"Wake Planner {person.name}",
        "manufacturer": "Benni's Toolbox",
        "model": "Wake Planner",
    }


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: Platform
) -> list:
    coordinator = coordinator_from_hass(hass, entry.entry_id)
    if coordinator is None:
        return []
    if platform == Platform.SENSOR:
        return [
            WakePlannerSensor(coordinator, entry, person, desc)
            for person in coordinator.persons
            for desc in SENSOR_DESCRIPTIONS
        ]
    if platform == Platform.BINARY_SENSOR:
        return [
            WakeNeededBinarySensor(coordinator, entry, person)
            for person in coordinator.persons
        ]
    return []


class WakePlannerSensor(CoordinatorEntity[WakePlannerCoordinator], SensorEntity):
    entity_description: SensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WakePlannerCoordinator,
        entry: ConfigEntry,
        person: PersonConfig,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.person = person
        self.entity_description = description
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, person.slug, description.key)
        self._attr_translation_key = description.translation_key
        self._attr_device_info = _device_info(entry, person)

    @property
    def native_value(self) -> str | datetime | None:
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        if self.entity_description.key == "wake_state":
            return decision.state.value if decision else None
        if self.entity_description.key == "next_wake":
            return self.coordinator.next_wakes.get(self.person.slug)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        if not decision:
            return {}
        attrs = decision.as_dict()
        attrs["person_id"] = self.person.slug
        if self.entity_description.key == "wake_state":
            attrs["wake_window_minutes"] = self.person.wake_window_minutes
            attrs["rules"] = [rule_to_dict(r) for r in self.person.rules]
            opts = self.coordinator.options
            attrs["holiday_behavior"] = opts.get(CONF_HOLIDAY_BEHAVIOR, HOLIDAY_SKIP)
            attrs["manual_holiday_dates"] = opts.get(CONF_MANUAL_HOLIDAY_DATES, "")
        return attrs


class WakeNeededBinarySensor(CoordinatorEntity[WakePlannerCoordinator], BinarySensorEntity):
    entity_description = BINARY_DESCRIPTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WakePlannerCoordinator,
        entry: ConfigEntry,
        person: PersonConfig,
    ) -> None:
        super().__init__(coordinator)
        self.person = person
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, person.slug, "wake_needed")
        self._attr_translation_key = BINARY_DESCRIPTION.translation_key
        self._attr_device_info = _device_info(entry, person)

    @property
    def is_on(self) -> bool:
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        if not decision or decision.state not in {WakeState.SCHEDULED, WakeState.OVERRIDDEN}:
            return False
        if not decision.wake_window_start or not decision.wake_window_end:
            return False
        now = dt_util.now()
        return dt_util.as_local(decision.wake_window_start) <= now <= dt_util.as_local(decision.wake_window_end)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        return decision.as_dict() if decision else {}
