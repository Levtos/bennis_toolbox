"""Binary sensor entities."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BenniMediaCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coord: BenniMediaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        _HeadsetActive(coord, entry),
        _EntertainmentActive(coord, entry),
        _QuietModeActive(coord, entry),
        _SubwooferAllowed(coord, entry),
    ])


class _Base(CoordinatorEntity[BenniMediaCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord: BenniMediaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coord)
        self._entry = entry

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_{self._key}"

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data
        return {
            "context": d.context,
            "subcontext": d.subcontext,
            "active_reasons": d.active_reasons,
        }


class _HeadsetActive(_Base):
    _key = "headset_active"
    _attr_name = "Headset Active"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.headset_active


class _EntertainmentActive(_Base):
    _key = "entertainment_active"
    _attr_name = "Entertainment Active"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.entertainment_active


class _QuietModeActive(_Base):
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


class _SubwooferAllowed(_Base):
    _key = "subwoofer_allowed"
    _attr_name = "Subwoofer Allowed"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.subwoofer_allowed
