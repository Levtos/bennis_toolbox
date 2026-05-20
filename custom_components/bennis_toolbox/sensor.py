"""Health-/Status-Sensoren für die Toolbox.

- 1 Overall-Sensor: bennis_toolbox status (z.B. "8/8 healthy")
- 1 Sensor je bekannter Teilintegration mit Statusattributen
Bewusst keine binary_sensor-Flut, keine fachlichen Werte.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, KNOWN_MEMBERS
from .status import collect_member_status


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[SensorEntity] = [ToolboxOverallSensor(entry)]
    entities.extend(ToolboxMemberSensor(entry, domain, name) for domain, name, _ in KNOWN_MEMBERS)
    async_add_entities(entities, update_before_add=True)


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Benni's Toolbox",
            "manufacturer": "Benni",
            "model": "Toolbox Hub",
            "entry_type": "service",
        }


class ToolboxOverallSensor(_Base):
    _attr_icon = "mdi:toolbox"
    _attr_translation_key = "overall"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_overall"
        self._attr_name = "Status"
        self._state: str = "unknown"
        self._attrs: dict = {}

    @property
    def native_value(self) -> str:
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        return self._attrs

    async def async_update(self) -> None:
        statuses = await collect_member_status(self.hass)
        healthy = sum(1 for s in statuses if s.healthy)
        installed = sum(1 for s in statuses if s.installed)
        total = len(statuses)
        self._state = f"{healthy}/{total} healthy"
        self._attrs = {
            "total": total,
            "installed": installed,
            "healthy": healthy,
            "members": [s.as_dict() for s in statuses],
        }


class ToolboxMemberSensor(_Base):
    _attr_icon = "mdi:puzzle"

    def __init__(self, entry: ConfigEntry, domain: str, friendly_name: str) -> None:
        super().__init__(entry)
        self._domain = domain
        self._friendly_name = friendly_name
        self._attr_unique_id = f"{entry.entry_id}_member_{domain}"
        self._attr_name = friendly_name
        self._state: str = "unknown"
        self._attrs: dict = {}

    @property
    def native_value(self) -> str:
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        return self._attrs

    async def async_update(self) -> None:
        statuses = await collect_member_status(self.hass)
        match = next((s for s in statuses if s.domain == self._domain), None)
        if match is None:
            self._state = "unknown"
            self._attrs = {}
            return
        if not match.installed:
            self._state = "missing"
        elif not match.loaded:
            self._state = "not_loaded"
        elif match.healthy:
            self._state = "healthy"
        else:
            self._state = "warning"
        self._attrs = match.as_dict()
