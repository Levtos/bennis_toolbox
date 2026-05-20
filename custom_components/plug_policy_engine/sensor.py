"""Sensors: summary + per-device policy state / decision / last action."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BenniPlugCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: BenniPlugCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [SummarySensor(coord)]
    for dev_id in coord.configs:
        entities.append(PolicyStateSensor(coord, dev_id))
        entities.append(DecisionSensor(coord, dev_id))
        entities.append(LastActionSensor(coord, dev_id))
    async_add_entities(entities)


class _Base(SensorEntity):
    _attr_should_poll = False

    def __init__(self, coord: BenniPlugCoordinator) -> None:
        self.coord = coord

    async def async_added_to_hass(self) -> None:
        self.coord.add_listener(self._sched_update)

    async def async_will_remove_from_hass(self) -> None:
        self.coord.remove_listener(self._sched_update)

    @callback
    def _sched_update(self) -> None:
        self.async_write_ha_state()


class SummarySensor(_Base):
    _attr_name = "Benni Plug Policy Summary"
    _attr_unique_id = "plug_policy_engine_summary"
    _attr_icon = "mdi:power-plug-outline"

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


class _PerDevice(_Base):
    def __init__(self, coord: BenniPlugCoordinator, dev_id: str) -> None:
        super().__init__(coord)
        self.dev_id = dev_id
        self._cfg = coord.configs[dev_id]

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self.dev_id)},
            "name": self._cfg.name,
            "manufacturer": "plug_policy_engine",
            "model": self._cfg.kind,
        }


class PolicyStateSensor(_PerDevice):
    @property
    def name(self) -> str:
        return f"{self._cfg.name} plug policy state"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.dev_id}_policy_state"

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


class DecisionSensor(_PerDevice):
    @property
    def name(self) -> str:
        return f"{self._cfg.name} plug decision"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.dev_id}_decision"

    @property
    def native_value(self) -> str:
        d = self.coord.decisions.get(self.dev_id)
        return d.desired_switch_state if d else "unknown"

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coord.decisions.get(self.dev_id)
        return d.to_attrs() if d else {}


class LastActionSensor(_PerDevice):
    @property
    def name(self) -> str:
        return f"{self._cfg.name} last policy action"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.dev_id}_last_action"

    @property
    def native_value(self) -> str:
        la = self.coord.last_action.get(self.dev_id) or {}
        return la.get("action", "none")

    @property
    def extra_state_attributes(self) -> dict:
        return self.coord.last_action.get(self.dev_id) or {}
