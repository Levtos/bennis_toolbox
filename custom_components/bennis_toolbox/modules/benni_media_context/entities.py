"""Sensor + Binary-Sensor-Entities für Benni Media Context."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import DOMAIN, unique_id
from .const import MODULE_ID
from .coordinator import BenniMediaCoordinator, coordinator_from_hass


def _device_info(entry: ConfigEntry) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, f"{MODULE_ID}_{entry.entry_id}")},
        "name": "Benni Media Context",
        "manufacturer": "Benni's Toolbox",
        "model": "Media Context",
    }


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: Platform
) -> list:
    coord = coordinator_from_hass(hass, entry.entry_id)
    if coord is None:
        return []
    if platform == Platform.SENSOR:
        return [
            _ContextSensor(coord, entry),
            _SubcontextSensor(coord, entry),
            _DeviceSensor(coord, entry),
            _GamingSourceSensor(coord, entry),
            _GamingPlatformSensor(coord, entry),
            _VolHomePodsSensor(coord, entry),
            _VolDenonSensor(coord, entry),
        ]
    if platform == Platform.BINARY_SENSOR:
        return [
            _HeadsetActive(coord, entry),
            _EntertainmentActive(coord, entry),
            _QuietModeActive(coord, entry),
            _SubwooferAllowed(coord, entry),
        ]
    return []


# --------------------------------------------------------------------- sensor


class _BaseSensor(CoordinatorEntity[BenniMediaCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _key: str = ""

    def __init__(self, coord: BenniMediaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coord)
        self._entry = entry
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, self._key)
        self._attr_device_info = _device_info(entry)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        return {
            "subcontext": d.subcontext,
            "device": d.device,
            "gaming_source": d.gaming_source,
            "gaming_platform": d.gaming_platform,
            "headset_active": d.headset_active,
            "entertainment_active": d.entertainment_active,
            "quiet_mode_active": d.quiet_mode_active,
            "quiet_mode_reason": d.quiet_mode_reason,
            "active_reasons": d.active_reasons,
            "volume_target_homepods": d.volume_target_homepods,
            "volume_target_denon": d.volume_target_denon,
            "subwoofer_allowed": d.subwoofer_allowed,
        }


class _ContextSensor(_BaseSensor):
    _key = "media_context"
    _attr_name = "Media Context"
    _attr_translation_key = "media_context"

    @property
    def native_value(self):
        return self.coordinator.data.context


class _SubcontextSensor(_BaseSensor):
    _key = "media_subcontext"
    _attr_name = "Media Subcontext"
    _attr_translation_key = "media_subcontext"

    @property
    def native_value(self):
        return self.coordinator.data.subcontext


class _DeviceSensor(_BaseSensor):
    _key = "media_device"
    _attr_name = "Media Device"

    @property
    def native_value(self):
        return self.coordinator.data.device


class _GamingSourceSensor(_BaseSensor):
    _key = "gaming_source"
    _attr_name = "Gaming Source"

    @property
    def native_value(self):
        return self.coordinator.data.gaming_source


class _GamingPlatformSensor(_BaseSensor):
    _key = "gaming_platform"
    _attr_name = "Gaming Platform"

    @property
    def native_value(self):
        return self.coordinator.data.gaming_platform


class _VolHomePodsSensor(_BaseSensor):
    _key = "volume_target_homepods"
    _attr_name = "Media Volume Target HomePods"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return round(self.coordinator.data.volume_target_homepods, 3)


class _VolDenonSensor(_BaseSensor):
    _key = "volume_target_denon"
    _attr_name = "Media Volume Target Denon"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return round(self.coordinator.data.volume_target_denon, 3)


# -------------------------------------------------------------- binary_sensor


class _BaseBinary(CoordinatorEntity[BenniMediaCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _key: str = ""

    def __init__(self, coord: BenniMediaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coord)
        self._entry = entry
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, self._key)
        self._attr_device_info = _device_info(entry)

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data
        return {
            "context": d.context,
            "subcontext": d.subcontext,
            "active_reasons": d.active_reasons,
        }


class _HeadsetActive(_BaseBinary):
    _key = "headset_active"
    _attr_name = "Headset Active"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.headset_active


class _EntertainmentActive(_BaseBinary):
    _key = "entertainment_active"
    _attr_name = "Entertainment Active"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.entertainment_active


class _QuietModeActive(_BaseBinary):
    _key = "quiet_mode_active"
    _attr_name = "Quiet Mode Active"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.quiet_mode_active

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        attrs["quiet_mode_reason"] = self.coordinator.data.quiet_mode_reason
        return attrs


class _SubwooferAllowed(_BaseBinary):
    _key = "subwoofer_allowed"
    _attr_name = "Subwoofer Allowed"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.subwoofer_allowed
