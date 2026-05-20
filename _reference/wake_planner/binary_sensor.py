"""Wake Planner binary sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, PersonConfig, WakeState
from .coordinator import WakePlannerCoordinator

DESCRIPTION = BinarySensorEntityDescription(
    key="wake_needed",
    translation_key="wake_needed",
    device_class=BinarySensorDeviceClass.RUNNING,
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up binary sensors for every configured person."""
    coordinator: WakePlannerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(WakeNeededBinarySensor(coordinator, entry, person) for person in coordinator.persons)

class WakeNeededBinarySensor(CoordinatorEntity[WakePlannerCoordinator], BinarySensorEntity):
    """True while the active wake window is open."""

    entity_description = DESCRIPTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: WakePlannerCoordinator, entry: ConfigEntry, person: PersonConfig) -> None:
        super().__init__(coordinator)
        self.person = person
        self._attr_unique_id = f"{entry.entry_id}_{person.slug}_wake_needed"
        self._attr_translation_key = DESCRIPTION.translation_key
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_{person.slug}")},
            "name": f"Wake Planner {person.name}",
            "manufacturer": "Wake Planner",
        }

    @property
    def is_on(self) -> bool:
        """Return true within the current wake window."""
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        if not decision or decision.state not in {WakeState.SCHEDULED, WakeState.OVERRIDDEN}:
            return False
        if not decision.wake_window_start or not decision.wake_window_end:
            return False
        now = dt_util.now()
        start = dt_util.as_local(decision.wake_window_start)
        end = dt_util.as_local(decision.wake_window_end)
        return start <= now <= end

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed decision attributes."""
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        return decision.as_dict() if decision else {}
