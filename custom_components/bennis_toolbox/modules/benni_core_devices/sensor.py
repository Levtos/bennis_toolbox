"""SensorEntities für Benni Core · Devices.

Pro Device-Instanz:
- Haupt-Sensor `sensor.benni_device_<slug>` (immer)
- Optional Sekundär-Sensoren bei `expose_secondary_sensors=true`:
  - `sensor.benni_device_<slug>_power_state`
  - `sensor.benni_device_<slug>_watt`  (nur wenn watt_sensor konfiguriert)

binary_sensor.py liefert die boolean-Sekundär-Sensoren (powered/available).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import DOMAIN, unique_id
from .const import (
    CONF_WATT_SENSOR,
    MODULE_ID,
    POWER_STATE_SLUGS,
)
from .coordinator import DeviceCoordinator, coordinator_from_hass
from .logic import DeviceResult


def _object_id(slug: str, suffix: str | None = None) -> str:
    base = f"benni_device_{slug}"
    return f"{base}_{suffix}" if suffix else base


def _device_info(coordinator: DeviceCoordinator) -> DeviceInfo:
    """HA-Device pro Config-Entry, damit Haupt- + Sekundär-Sensoren unter
    einer Geräte-Karte gruppiert erscheinen (Benni Core · Devices)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{MODULE_ID}:{coordinator.slug}")},
        name=coordinator.display_name,
        manufacturer="Benni Core · Devices",
        model=coordinator.device_type.value,
    )


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: str
) -> list[Entity]:
    if platform != Platform.SENSOR:
        return []
    coordinator = coordinator_from_hass(hass, entry)
    if coordinator is None:
        return []
    out: list[Entity] = [DeviceMainSensor(coordinator, entry)]
    if coordinator.expose_secondary_sensors:
        out.append(PowerStateSensor(coordinator, entry))
        if coordinator.watt_slot_key:
            out.append(WattSensor(coordinator, entry))
    return out


class _BaseDeviceSensor(CoordinatorEntity[DeviceCoordinator], SensorEntity):
    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: DeviceCoordinator,
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
        self._attr_device_info = _device_info(coordinator)

    @property
    def _result(self) -> DeviceResult | None:
        return self.coordinator.data


class DeviceMainSensor(_BaseDeviceSensor):
    """Der EINE konsolidierte Sensor pro Device."""

    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: DeviceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            suffix="main",
            object_id=_object_id(coordinator.slug),
            name=coordinator.display_name,
        )

    @property
    def native_value(self) -> str | None:
        r = self._result
        return r.state if r else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self._result
        if r is None:
            return {}
        c = self.coordinator
        attrs: dict[str, Any] = {
            "device_type": c.device_type.value,
            "slug": c.slug,
            "display_name": c.display_name,
            "powered": r.powered,
            "power_state": r.power_state,
            "available": r.available,
            "power_source": r.power_source,
            "last_powered_change": r.last_powered_change,
            "override_active": r.override_active,
            "watt_disagrees": r.watt_disagrees,
            "area_id": c._derive_area_id(),
        }
        # Typspezifische Extra-Attribute (LH §6)
        from .device_types import profile_for

        profile = profile_for(c.device_type)
        for key in profile.extra_attributes:
            if key == "watt":
                attrs[key] = r.watt
            elif key == "media_player_state":
                attrs[key] = r.raw_state if profile.state_slot else None
            else:
                attrs[key] = r.extra.get(key)
        return attrs


class PowerStateSensor(_BaseDeviceSensor):
    """Optionaler Sekundär-Sensor: aus Watt-Buckets abgeleiteter power_state."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(POWER_STATE_SLUGS)
    _attr_icon = "mdi:flash"

    def __init__(self, coordinator: DeviceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            suffix="power_state",
            object_id=_object_id(coordinator.slug, "power_state"),
            name=f"{coordinator.display_name} Power State",
        )

    @property
    def native_value(self) -> str | None:
        r = self._result
        return r.power_state if r else None


class WattSensor(_BaseDeviceSensor):
    """Optionaler Sekundär-Sensor: numerischer Watt-Wert."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "W"
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator: DeviceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            suffix="watt",
            object_id=_object_id(coordinator.slug, "watt"),
            name=f"{coordinator.display_name} Watt",
        )

    @property
    def native_value(self) -> float | None:
        r = self._result
        return r.watt if r else None
