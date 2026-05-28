"""BinarySensor-Entities für Benni Core · Devices.

Nur aktiv wenn `expose_secondary_sensors=true`:
- `binary_sensor.benni_device_<slug>_powered`
- `binary_sensor.benni_device_<slug>_available`
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import unique_id
from .const import MODULE_ID
from .coordinator import DeviceCoordinator, coordinator_from_hass
from .logic import DeviceResult


def _object_id(slug: str, suffix: str) -> str:
    return f"benni_device_{slug}_{suffix}"


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: str
) -> list[Entity]:
    if platform != Platform.BINARY_SENSOR:
        return []
    coordinator = coordinator_from_hass(hass, entry)
    if coordinator is None or not coordinator.expose_secondary_sensors:
        return []
    return [
        PoweredBinarySensor(coordinator, entry),
        AvailableBinarySensor(coordinator, entry),
    ]


class _BaseDeviceBinarySensor(
    CoordinatorEntity[DeviceCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: DeviceCoordinator,
        entry: ConfigEntry,
        *,
        suffix: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, suffix)
        self._attr_suggested_object_id = _object_id(coordinator.slug, suffix)
        self._attr_name = name

    @property
    def _result(self) -> DeviceResult | None:
        return self.coordinator.data


class PoweredBinarySensor(_BaseDeviceBinarySensor):
    _attr_icon = "mdi:power-plug"

    def __init__(self, coordinator: DeviceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            suffix="powered",
            name=f"{coordinator.display_name} Powered",
        )

    @property
    def is_on(self) -> bool | None:
        r = self._result
        return r.powered if r else None


class AvailableBinarySensor(_BaseDeviceBinarySensor):
    _attr_icon = "mdi:check-network"

    def __init__(self, coordinator: DeviceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            suffix="available",
            name=f"{coordinator.display_name} Available",
        )

    @property
    def is_on(self) -> bool | None:
        r = self._result
        return r.available if r else None
