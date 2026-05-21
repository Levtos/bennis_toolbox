"""Entities für Cover Policy: 3 Sensoren + 1 Binary-Sensor + 1 Diagnostic."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory

from ...const import DOMAIN, unique_id
from .const import (
    CONF_COVER_ENTITY,
    MODULE_ID,
    UID_APPLY_BLOCKED,
    UID_DEBUG,
    UID_MODE,
    UID_REASON,
    UID_TARGET,
)
from .coordinator import CoverPolicyCoordinator, coordinator_from_hass


def _base_slug(entry: ConfigEntry) -> str:
    """Derive a sensible object-id stem from the configured cover entity.

    `cover.living_blackout_blind` → `living_blackout_blind`. Used purely
    for `suggested_object_id` on entity creation; unique_id is untouched
    so existing entries keep their identity even if the cover entity is
    later swapped out.
    """
    cover = (entry.data.get(CONF_COVER_ENTITY) or "").strip()
    if "." in cover:
        cover = cover.split(".", 1)[1]
    # Fall back to the entry-id slug when no cover entity is configured —
    # better than an empty object_id that HA would auto-suffix with random
    # noise.
    return cover or f"cover_policy_{entry.entry_id}"


def _suggested_id(entry: ConfigEntry, suffix: str) -> str:
    return f"{_base_slug(entry)}_{suffix}"


def _device_info(entry: ConfigEntry) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, f"{MODULE_ID}_{entry.entry_id}")},
        "name": entry.title or "Cover Policy",
        "manufacturer": "Benni's Toolbox",
        "model": "Cover Policy",
    }


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: Platform
) -> list:
    coord = coordinator_from_hass(hass, entry.entry_id)
    if coord is None:
        return []
    if platform == Platform.SENSOR:
        return [
            ModeSensor(coord, entry),
            TargetPositionSensor(coord, entry),
            ReasonSensor(coord, entry),
            DebugSensor(coord, entry),
        ]
    if platform == Platform.BINARY_SENSOR:
        return [ApplyBlockedBinarySensor(coord, entry)]
    return []


class _SubscribingMixin:
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coord: CoverPolicyCoordinator, entry: ConfigEntry) -> None:
        self.coord = coord
        self._entry = entry
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.coord.add_listener(self._sched_update)

    async def async_will_remove_from_hass(self) -> None:
        self.coord.remove_listener(self._sched_update)

    @callback
    def _sched_update(self) -> None:
        self.async_write_ha_state()


class ModeSensor(_SubscribingMixin, SensorEntity):
    _attr_icon = "mdi:roller-shade"

    def __init__(self, coord, entry):
        _SubscribingMixin.__init__(self, coord, entry)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, UID_MODE)
        self._attr_name = "Cover Mode"
        self._attr_suggested_object_id = _suggested_id(entry, "cover_mode")

    @property
    def native_value(self) -> str | None:
        d = self.coord.last_decision
        return d.mode if d else None


class TargetPositionSensor(_SubscribingMixin, SensorEntity):
    _attr_icon = "mdi:roller-shade-closed"
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coord, entry):
        _SubscribingMixin.__init__(self, coord, entry)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, UID_TARGET)
        self._attr_name = "Target Position"
        self._attr_suggested_object_id = _suggested_id(entry, "target_position")

    @property
    def native_value(self) -> int | None:
        d = self.coord.last_decision
        return d.target_position if d else None


class ReasonSensor(_SubscribingMixin, SensorEntity):
    _attr_icon = "mdi:script-text-outline"

    def __init__(self, coord, entry):
        _SubscribingMixin.__init__(self, coord, entry)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, UID_REASON)
        self._attr_name = "Policy Reason"
        self._attr_suggested_object_id = _suggested_id(entry, "policy_reason")

    @property
    def native_value(self) -> str | None:
        d = self.coord.last_decision
        return d.reason if d else None

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coord.last_decision
        if not d:
            return {}
        return {
            "blockers": list(d.blockers),
            "apply_allowed": d.apply_allowed,
            "manual_override_active": self.coord.manual_override_active(),
        }


class ApplyBlockedBinarySensor(_SubscribingMixin, BinarySensorEntity):
    _attr_icon = "mdi:lock-alert"

    def __init__(self, coord, entry):
        _SubscribingMixin.__init__(self, coord, entry)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, UID_APPLY_BLOCKED)
        self._attr_name = "Apply Blocked"
        self._attr_suggested_object_id = _suggested_id(entry, "apply_blocked")

    @property
    def is_on(self) -> bool:
        d = self.coord.last_decision
        return bool(d and not d.apply_allowed)

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coord.last_decision
        return {"blockers": list(d.blockers) if d else []}


class DebugSensor(_SubscribingMixin, SensorEntity):
    _attr_icon = "mdi:bug-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord, entry):
        _SubscribingMixin.__init__(self, coord, entry)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, UID_DEBUG)
        self._attr_name = "Policy Debug"
        self._attr_suggested_object_id = _suggested_id(entry, "policy_debug")

    @property
    def native_value(self) -> str | None:
        d = self.coord.last_decision
        return d.mode if d else None

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coord.last_decision
        if not d:
            return {"profile": self.coord.profile}
        return {
            "decision": d.as_dict(),
            "profile": self.coord.profile,
            "manual_override_active": self.coord.manual_override_active(),
        }
