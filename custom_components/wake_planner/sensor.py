"""Wake Planner sensors."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HOLIDAY_BEHAVIOR, CONF_MANUAL_HOLIDAY_DATES, DOMAIN, HOLIDAY_SKIP, PersonConfig
from .coordinator import WakePlannerCoordinator
from .util import rule_to_dict

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key="wake_state", translation_key="wake_state"),
    SensorEntityDescription(
        key="next_wake", translation_key="next_wake", device_class=SensorDeviceClass.TIMESTAMP
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WakePlannerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WakePlannerSensor(coordinator, entry, person, description)
        for person in coordinator.persons
        for description in SENSOR_TYPES
    )


class WakePlannerSensor(CoordinatorEntity[WakePlannerCoordinator], SensorEntity):
    """A Wake Planner sensor."""

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
        self._attr_unique_id = f"{entry.entry_id}_{person.slug}_{description.key}"
        self._attr_translation_key = description.translation_key
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_{person.slug}")},
            "name": f"Wake Planner {person.name}",
            "manufacturer": "Wake Planner",
        }

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
