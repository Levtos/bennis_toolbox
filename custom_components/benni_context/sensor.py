"""Sensor entities for Benni Context."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ACTIVITY_STATES,
    BIO_STATES,
    DAY_CONTEXT_STATES,
    DAY_STATES,
    DOMAIN,
    PRESENCE_BAND_STATES,
    PRESENCE_HOUSEHOLD_STATES,
    PRESENCE_PERSONAL_STATES,
    PRESENCE_TRANSITION_STATES,
)
from .coordinator import BenniContextCoordinator
from .models import ComputedState


@dataclass(frozen=True)
class BenniSensorDescription:
    key: str
    name: str
    options: list[str] | None
    value_fn: Callable[[ComputedState], str]
    attr_key: str | None = None


SENSORS: tuple[BenniSensorDescription, ...] = (
    BenniSensorDescription(
        key="presence_personal",
        name="Presence Personal",
        options=PRESENCE_PERSONAL_STATES,
        value_fn=lambda s: s.presence_personal,
        attr_key="presence_personal",
    ),
    BenniSensorDescription(
        key="presence_household",
        name="Presence Household",
        options=PRESENCE_HOUSEHOLD_STATES,
        value_fn=lambda s: s.presence_household,
    ),
    BenniSensorDescription(
        key="presence_band",
        name="Presence Band",
        options=PRESENCE_BAND_STATES,
        value_fn=lambda s: s.presence_band,
        attr_key="presence_band",
    ),
    BenniSensorDescription(
        key="presence_transition",
        name="Presence Transition",
        options=PRESENCE_TRANSITION_STATES,
        value_fn=lambda s: s.presence_transition,
        attr_key="presence_transition",
    ),
    BenniSensorDescription(
        key="bio_state",
        name="Bio State",
        options=BIO_STATES,
        value_fn=lambda s: s.bio_state,
        attr_key="bio_state",
    ),
    BenniSensorDescription(
        key="day_state",
        name="Day State",
        options=DAY_STATES,
        value_fn=lambda s: s.day_state,
    ),
    BenniSensorDescription(
        key="day_context",
        name="Day Context",
        options=DAY_CONTEXT_STATES,
        value_fn=lambda s: s.day_context,
    ),
    BenniSensorDescription(
        key="activity_state",
        name="Activity State",
        options=ACTIVITY_STATES,
        value_fn=lambda s: s.activity_state,
        attr_key="activity_state",
    ),
    BenniSensorDescription(
        key="master_context",
        name="Master Context",
        options=None,
        value_fn=lambda s: s.master_context,
        attr_key="master_context",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BenniContextCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(BenniSensor(coordinator, desc) for desc in SENSORS)


class BenniSensor(CoordinatorEntity[BenniContextCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BenniContextCoordinator,
        description: BenniSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self._desc = description
        self._attr_name = description.name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        if description.options:
            self._attr_device_class = "enum"
            self._attr_options = description.options

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self._desc.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None or not self._desc.attr_key:
            return {}
        return self.coordinator.data.attrs.get(self._desc.attr_key, {})

    @property
    def available(self) -> bool:
        # The master context and presence sensors must remain available even
        # when individual inputs are missing: they fall back to documented
        # defaults rather than going "unavailable".
        return self.coordinator.last_update_success or self.coordinator.data is not None
