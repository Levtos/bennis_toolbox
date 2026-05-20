"""Sensor + Binary-Sensor Entities für Plug Policy Engine.

Pro Entry liefern wir:
- 1 Summary-Sensor (cutting/applying/mixed/idle)
- 1 AnyBlocked-Binary-Sensor
- pro Device: PolicyState-, Decision-, LastAction-Sensor + Active-Binary-Sensor
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback

from ...const import DOMAIN, unique_id
from .const import MODULE_ID
from .coordinator import PlugPolicyCoordinator, coordinator_from_hass


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: Platform
) -> list:
    coord = coordinator_from_hass(hass, entry.entry_id)
    if coord is None:
        return []
    if platform == Platform.SENSOR:
        out: list = [SummarySensor(coord, entry)]
        for dev_id in coord.configs:
            out.append(PolicyStateSensor(coord, entry, dev_id))
            out.append(DecisionSensor(coord, entry, dev_id))
            out.append(LastActionSensor(coord, entry, dev_id))
        return out
    if platform == Platform.BINARY_SENSOR:
        out2: list = [AnyBlockedSensor(coord, entry)]
        for dev_id in coord.configs:
            out2.append(DeviceActiveSensor(coord, entry, dev_id))
        return out2
    return []


def _entry_device_info(entry: ConfigEntry) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, f"{MODULE_ID}_{entry.entry_id}")},
        "name": "Plug Policy Engine",
        "manufacturer": "Benni's Toolbox",
        "model": "Plug Policy",
    }


def _dev_device_info(entry: ConfigEntry, dev_id: str, cfg) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, f"{MODULE_ID}_{entry.entry_id}_{dev_id}")},
        "name": cfg.name,
        "manufacturer": "Benni's Toolbox",
        "model": f"Plug · {cfg.kind}",
    }


# -------------------------------------------------------------- summary


class _ListenerMixin:
    """Manuelles Listener-Pattern; der Coordinator ist kein DataUpdateCoordinator."""

    _attr_should_poll = False

    def __init__(self, coord: PlugPolicyCoordinator) -> None:
        self.coord = coord

    async def async_added_to_hass(self) -> None:
        self.coord.add_listener(self._sched_update)

    async def async_will_remove_from_hass(self) -> None:
        self.coord.remove_listener(self._sched_update)

    @callback
    def _sched_update(self) -> None:
        self.async_write_ha_state()


class SummarySensor(_ListenerMixin, SensorEntity):
    _attr_name = "Plug Policy Summary"
    _attr_icon = "mdi:power-plug-outline"
    _attr_has_entity_name = True

    def __init__(self, coord: PlugPolicyCoordinator, entry: ConfigEntry) -> None:
        _ListenerMixin.__init__(self, coord)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, "summary")
        self._attr_device_info = _entry_device_info(entry)

    @property
    def native_value(self) -> str:
        if not self.coord.decisions:
            return "idle"
        any_off = any(d.desired_switch_state == "off" for d in self.coord.decisions.values())
        any_on = any(d.desired_switch_state == "on" for d in self.coord.decisions.values())
        if any_off and any_on:
            return "mixed"
        if any_off:
            return "cutting"
        if any_on:
            return "applying"
        return "idle"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "devices": {dev_id: d.to_attrs() for dev_id, d in self.coord.decisions.items()},
            "enable_control": self.coord.enable_control,
        }


class AnyBlockedSensor(_ListenerMixin, BinarySensorEntity):
    _attr_name = "Plug Policy Any Blocked"
    _attr_icon = "mdi:shield-alert"
    _attr_has_entity_name = True

    def __init__(self, coord: PlugPolicyCoordinator, entry: ConfigEntry) -> None:
        _ListenerMixin.__init__(self, coord)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, "any_blocked")
        self._attr_device_info = _entry_device_info(entry)

    @property
    def is_on(self) -> bool:
        return any(bool(d.blockers) for d in self.coord.decisions.values())

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "blocked_devices": {
                dev_id: d.blockers
                for dev_id, d in self.coord.decisions.items() if d.blockers
            }
        }


# -------------------------------------------------------------- per device


class _PerDeviceBase(_ListenerMixin):
    def __init__(
        self,
        coord: PlugPolicyCoordinator,
        entry: ConfigEntry,
        dev_id: str,
        suffix: str,
    ) -> None:
        _ListenerMixin.__init__(self, coord)
        self.dev_id = dev_id
        self._entry = entry
        self._cfg = coord.configs[dev_id]
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, dev_id, suffix)
        self._attr_device_info = _dev_device_info(entry, dev_id, self._cfg)


class PolicyStateSensor(_PerDeviceBase, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, entry, dev_id):
        super().__init__(coord, entry, dev_id, "policy_state")
        self._attr_name = f"{self._cfg.name} policy state"

    @property
    def native_value(self) -> str:
        return self._cfg.policy

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "kind": self._cfg.kind,
            "switch_entity": self._cfg.switch_entity,
            "suspended": self.coord.states[self.dev_id].suspended,
        }


class DecisionSensor(_PerDeviceBase, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, entry, dev_id):
        super().__init__(coord, entry, dev_id, "decision")
        self._attr_name = f"{self._cfg.name} decision"

    @property
    def native_value(self) -> str:
        d = self.coord.decisions.get(self.dev_id)
        return d.desired_switch_state if d else "unknown"

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coord.decisions.get(self.dev_id)
        return d.to_attrs() if d else {}


class LastActionSensor(_PerDeviceBase, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, entry, dev_id):
        super().__init__(coord, entry, dev_id, "last_action")
        self._attr_name = f"{self._cfg.name} last action"

    @property
    def native_value(self) -> str:
        la = self.coord.last_action.get(self.dev_id) or {}
        return la.get("action", "none")

    @property
    def extra_state_attributes(self) -> dict:
        return self.coord.last_action.get(self.dev_id) or {}


class DeviceActiveSensor(_PerDeviceBase, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, entry, dev_id):
        super().__init__(coord, entry, dev_id, "active")
        self._attr_name = f"{self._cfg.name} active"

    @property
    def is_on(self) -> bool:
        d = self.coord.decisions.get(self.dev_id)
        return bool(d and d.active_state == "active")

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coord.decisions.get(self.dev_id)
        return {
            "active_state": d.active_state if d else "unknown",
            "power_w": d.power_w if d else None,
        }
