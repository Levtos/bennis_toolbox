"""Binary sensors: any-blocked plus per-device active."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BenniPlugCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: BenniPlugCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [AnyBlockedSensor(coord)]
    for dev_id in coord.configs:
        entities.append(DeviceActiveSensor(coord, dev_id))
    async_add_entities(entities)


class _Base(BinarySensorEntity):
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


class AnyBlockedSensor(_Base):
    _attr_name = "Benni Plug Policy Any Blocked"
    _attr_unique_id = "plug_policy_engine_any_blocked"
    _attr_icon = "mdi:shield-alert"

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


class DeviceActiveSensor(_Base):
    def __init__(self, coord: BenniPlugCoordinator, dev_id: str) -> None:
        super().__init__(coord)
        self.dev_id = dev_id
        self._cfg = coord.configs[dev_id]

    @property
    def name(self) -> str:
        return f"{self._cfg.name} active"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.dev_id}_active"

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

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self.dev_id)},
            "name": self._cfg.name,
            "manufacturer": "plug_policy_engine",
            "model": self._cfg.kind,
        }
