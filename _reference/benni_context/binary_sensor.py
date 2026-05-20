"""Binary sensor entities for Benni Context."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BenniContextCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BenniContextCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PreheatActiveBinarySensor(coordinator)])


class PreheatActiveBinarySensor(
    CoordinatorEntity[BenniContextCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = True
    _attr_name = "Presence Preheat Active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: BenniContextCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_presence_preheat_active"
        )

    @property
    def is_on(self) -> bool:
        if self.coordinator.data is None:
            return False
        return bool(self.coordinator.data.preheat_active)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        return self.coordinator.data.attrs.get("preheat", {})
