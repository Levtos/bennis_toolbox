"""Wake-Planner-Entities (Sensor + Binary Sensor).

Werden vom Umbrella-Platform-Dispatcher über `async_get_entities` angefragt.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from ...const import DOMAIN, unique_id
from .const import (
    CONF_HOLIDAY_BEHAVIOR,
    CONF_MANUAL_HOLIDAY_DATES,
    HOLIDAY_SKIP,
    MODULE_ID,
    PersonConfig,
    WakeState,
)
from .coordinator import WakePlannerCoordinator, coordinator_from_hass
from .util import rule_to_dict


# `wake_state` is an enum sensor. As soon as the umbrella translations
# carry `entity.sensor.wake_state.state.*` keys, HA validates the value
# against `options`. If we don't declare them, every state is rejected
# and the sensor reports `unknown` — even though the underlying
# `WakeDecision.state` is correct. Pin both so the value flows through.
_WAKE_STATE_OPTIONS: list[str] = [s.value for s in WakeState]


SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="wake_state",
        translation_key="wake_state",
        device_class=SensorDeviceClass.ENUM,
        options=_WAKE_STATE_OPTIONS,
    ),
    SensorEntityDescription(
        key="next_wake",
        translation_key="next_wake",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)

BINARY_DESCRIPTION = BinarySensorEntityDescription(
    key="wake_needed",
    translation_key="wake_needed",
    device_class=BinarySensorDeviceClass.RUNNING,
)

# The holiday-active binary mirrors the wake-planner decision's
# "today is a holiday / day-off" flag so downstream consumers
# (benni_context.holiday_sensor) get a single clean boolean instead
# of having to parse the textual `decision.reason`.
HOLIDAY_ACTIVE_DESCRIPTION = BinarySensorEntityDescription(
    key="holiday_active",
    translation_key="holiday_active",
)


def _device_info(entry: ConfigEntry, person: PersonConfig) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, f"{MODULE_ID}_{entry.entry_id}_{person.slug}")},
        "name": f"Wake Planner {person.name}",
        "manufacturer": "Benni's Toolbox",
        "model": "Wake Planner",
    }


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: Platform
) -> list:
    coordinator = coordinator_from_hass(hass, entry.entry_id)
    if coordinator is None:
        return []
    if platform == Platform.SENSOR:
        return [
            WakePlannerSensor(coordinator, entry, person, desc)
            for person in coordinator.persons
            for desc in SENSOR_DESCRIPTIONS
        ]
    if platform == Platform.BINARY_SENSOR:
        entities: list = []
        for person in coordinator.persons:
            entities.append(WakeNeededBinarySensor(coordinator, entry, person))
            entities.append(HolidayActiveBinarySensor(coordinator, entry, person))
        return entities
    return []


class WakePlannerSensor(CoordinatorEntity[WakePlannerCoordinator], SensorEntity):
    entity_description: SensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WakePlannerCoordinator,
        entry: ConfigEntry,
        person: PersonConfig,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.person = person
        self.entity_description = description
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, person.slug, description.key)
        self._attr_translation_key = description.translation_key
        self._attr_device_info = _device_info(entry, person)
        # Suggested object_id derived from the entity's purpose, not from
        # the device-class. HA otherwise falls back to the device-class
        # translation (`Zeitstempel`, `Betriebszustand`), which is
        # semantically meaningless to downstream consumers like
        # benni_context. The unique_id stays unchanged so existing
        # registry entries keep their identity; only new entries pick
        # up the readable slug.
        self._attr_suggested_object_id = (
            f"{MODULE_ID}_{person.slug}_{description.key}"
        )

    @property
    def native_value(self) -> str | datetime | None:
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        if self.entity_description.key == "wake_state":
            return decision.state.value if decision else None
        if self.entity_description.key == "next_wake":
            return self.coordinator.next_wakes.get(self.person.slug)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        if not decision:
            return {}
        attrs = decision.as_dict()
        attrs["person_id"] = self.person.slug
        if self.entity_description.key == "wake_state":
            attrs["wake_window_minutes"] = self.person.wake_window_minutes
            attrs["rules"] = [rule_to_dict(r) for r in self.person.rules]
            opts = self.coordinator.options
            attrs["holiday_behavior"] = opts.get(CONF_HOLIDAY_BEHAVIOR, HOLIDAY_SKIP)
            attrs["manual_holiday_dates"] = opts.get(CONF_MANUAL_HOLIDAY_DATES, "")
        return attrs


class WakeNeededBinarySensor(CoordinatorEntity[WakePlannerCoordinator], BinarySensorEntity):
    entity_description = BINARY_DESCRIPTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WakePlannerCoordinator,
        entry: ConfigEntry,
        person: PersonConfig,
    ) -> None:
        super().__init__(coordinator)
        self.person = person
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, person.slug, "wake_needed")
        self._attr_translation_key = BINARY_DESCRIPTION.translation_key
        self._attr_device_info = _device_info(entry, person)
        # Same readable-object_id treatment as the timestamp sensor.
        # The unique_id is `…_wake_needed` so existing entries don't
        # break; new entries land on `binary_sensor.wake_planner_<slug>
        # _wake_needed` directly instead of HA's German device-class
        # fallback (`…_betriebszustand`).
        self._attr_suggested_object_id = (
            f"{MODULE_ID}_{person.slug}_wake_needed"
        )

    @property
    def is_on(self) -> bool:
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        if not decision or decision.state not in {WakeState.SCHEDULED, WakeState.OVERRIDDEN}:
            return False
        if not decision.wake_window_start or not decision.wake_window_end:
            return False
        now = dt_util.now()
        return dt_util.as_local(decision.wake_window_start) <= now <= dt_util.as_local(decision.wake_window_end)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        return decision.as_dict() if decision else {}


class HolidayActiveBinarySensor(CoordinatorEntity[WakePlannerCoordinator], BinarySensorEntity):
    """Boolean projection of the wake-planner decision for downstream
    consumers (e.g. ``benni_context.holiday_sensor``).

    ON if the current decision was driven by a holiday/profile-holiday
    rule — either ``decision.holiday_name`` is non-empty or
    ``decision.matched_rule_id == "profile_holiday"``. OFF otherwise
    (including weekday plans and missing-decision cold-start cases).
    """

    entity_description = HOLIDAY_ACTIVE_DESCRIPTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WakePlannerCoordinator,
        entry: ConfigEntry,
        person: PersonConfig,
    ) -> None:
        super().__init__(coordinator)
        self.person = person
        self._attr_unique_id = unique_id(
            MODULE_ID, entry.entry_id, person.slug, "holiday_active",
        )
        self._attr_translation_key = HOLIDAY_ACTIVE_DESCRIPTION.translation_key
        self._attr_device_info = _device_info(entry, person)
        self._attr_suggested_object_id = (
            f"{MODULE_ID}_{person.slug}_holiday_active"
        )

    @property
    def is_on(self) -> bool:
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        if not decision:
            return False
        if decision.holiday_name:
            return True
        if decision.matched_rule_id == "profile_holiday":
            return True
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        decision = self.coordinator.data.get(self.person.slug) if self.coordinator.data else None
        if not decision:
            return {}
        attrs: dict[str, Any] = {
            "holiday_name": decision.holiday_name,
            "reason": decision.reason,
            "decided_by": decision.decided_by,
            "matched_rule_id": decision.matched_rule_id,
            "next_wake": (
                decision.next_wake.isoformat() if decision.next_wake else None
            ),
            "wake_state": decision.state.value if decision.state else None,
            "person_id": self.person.slug,
        }
        return attrs
