"""SensorEntities für Benni Core · User State.

Drei Entities:
- `sensor.benni_core_user_bio_state` (enum: sleep/waking/awake)
- `sensor.benni_core_user_sleep_duration_minutes`
- `sensor.benni_core_user_awake_duration_minutes`

Alle drei lesen aus dem gemeinsamen UserStateCoordinator.
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
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import unique_id
from .const import BIO_STATE_SLUGS, MODULE_ID
from .coordinator import UserStateCoordinator, coordinator_from_hass
from .logic import UserStateResult

# Object-IDs (gemäß naming.md, aber mit benni_core_ Prefix für Owner-Klarheit).
OBJECT_ID_BIO_STATE = "benni_core_user_bio_state"
OBJECT_ID_SLEEP_DURATION = "benni_core_user_sleep_duration_minutes"
OBJECT_ID_AWAKE_DURATION = "benni_core_user_awake_duration_minutes"


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: str
) -> list[Entity]:
    if platform != Platform.SENSOR:
        return []
    coordinator = coordinator_from_hass(hass, entry)
    if coordinator is None:
        return []
    return [
        BioStateSensor(coordinator, entry),
        SleepDurationSensor(coordinator, entry),
        AwakeDurationSensor(coordinator, entry),
    ]


class _BaseUserStateSensor(CoordinatorEntity[UserStateCoordinator], SensorEntity):
    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: UserStateCoordinator,
        entry: ConfigEntry,
        *,
        suffix: str,
        object_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, suffix)
        self._attr_suggested_object_id = object_id

    @property
    def _result(self) -> UserStateResult | None:
        return self.coordinator.data


class BioStateSensor(_BaseUserStateSensor):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(BIO_STATE_SLUGS)
    _attr_icon = "mdi:bed"
    _attr_name = "Benni Core User Bio State"

    def __init__(
        self, coordinator: UserStateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(
            coordinator, entry, suffix="bio_state", object_id=OBJECT_ID_BIO_STATE
        )

    @property
    def native_value(self) -> str | None:
        r = self._result
        return r.bio_state.value if r else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self._result
        if r is None:
            return {}
        return {
            "sleep_started_at": r.sleep_started_at,
            "awake_started_at": r.awake_started_at,
            "sleep_duration_minutes": r.sleep_duration_minutes,
            "awake_duration_minutes": r.awake_duration_minutes,
            "last_trigger": r.trigger.value,
            "last_trigger_blocked": r.trigger_blocked,
            "last_trigger_blocked_reason": r.trigger_blocked_reason,
        }


class _DurationSensor(_BaseUserStateSensor):
    """Gemeinsame Basis für Sleep- und Awake-Duration-Sensoren."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT


class SleepDurationSensor(_DurationSensor):
    _attr_icon = "mdi:sleep"
    _attr_name = "Benni Core User Sleep Duration"

    def __init__(
        self, coordinator: UserStateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            suffix="sleep_duration",
            object_id=OBJECT_ID_SLEEP_DURATION,
        )

    @property
    def native_value(self) -> int | None:
        r = self._result
        return r.sleep_duration_minutes if r else None


class AwakeDurationSensor(_DurationSensor):
    _attr_icon = "mdi:weather-sunny"
    _attr_name = "Benni Core User Awake Duration"

    def __init__(
        self, coordinator: UserStateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            suffix="awake_duration",
            object_id=OBJECT_ID_AWAKE_DURATION,
        )

    @property
    def native_value(self) -> int | None:
        r = self._result
        return r.awake_duration_minutes if r else None
