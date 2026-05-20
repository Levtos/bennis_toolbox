"""Sensor entities."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BenniMediaCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coord: BenniMediaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        _ContextSensor(coord, entry),
        _SubcontextSensor(coord, entry),
        _DeviceSensor(coord, entry),
        _GamingSourceSensor(coord, entry),
        _GamingPlatformSensor(coord, entry),
        _VolHomePodsSensor(coord, entry),
        _VolDenonSensor(coord, entry),
    ])


class _Base(CoordinatorEntity[BenniMediaCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord: BenniMediaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coord)
        self._entry = entry

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_{self._key}"

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


class _ContextSensor(_Base):
    _key = "media_context"
    _attr_name = "Media Context"
    _attr_translation_key = "media_context"

    @property
    def native_value(self):
        return self.coordinator.data.context


class _SubcontextSensor(_Base):
    _key = "media_subcontext"
    _attr_name = "Media Subcontext"
    _attr_translation_key = "media_subcontext"

    @property
    def native_value(self):
        return self.coordinator.data.subcontext


class _DeviceSensor(_Base):
    _key = "media_device"
    _attr_name = "Media Device"

    @property
    def native_value(self):
        return self.coordinator.data.device


class _GamingSourceSensor(_Base):
    _key = "gaming_source"
    _attr_name = "Gaming Source"

    @property
    def native_value(self):
        return self.coordinator.data.gaming_source


class _GamingPlatformSensor(_Base):
    _key = "gaming_platform"
    _attr_name = "Gaming Platform"

    @property
    def native_value(self):
        return self.coordinator.data.gaming_platform


class _VolHomePodsSensor(_Base):
    _key = "volume_target_homepods"
    _attr_name = "Media Volume Target HomePods"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return round(self.coordinator.data.volume_target_homepods, 3)


class _VolDenonSensor(_Base):
    _key = "volume_target_denon"
    _attr_name = "Media Volume Target Denon"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return round(self.coordinator.data.volume_target_denon, 3)
