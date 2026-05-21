"""Entities des Notification-Router-Moduls.

Sensoren + Binary-Sensor lauschen auf den dispatcher-Signal
`bennis_toolbox_notification_router_state_updated` und ziehen ihre Werte
aus dem `NotificationRouter`-Runtime.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory

from ...const import DOMAIN, unique_id
from .const import (
    BINARY_SENSOR_DND,
    MODE_SILENT,
    MODULE_ID,
    SENSOR_LAST_EVENT,
    SENSOR_MODE,
)
from .coordinator import SIGNAL_STATE_UPDATED, NotificationRouter, router_from_hass


def _device_info(entry: ConfigEntry) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, f"{MODULE_ID}_{entry.entry_id}")},
        "name": "Notification Router",
        "manufacturer": "Benni's Toolbox",
        "model": "Notification Router",
    }


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: Platform
) -> list:
    router = router_from_hass(hass, entry.entry_id)
    if router is None:
        return []
    if platform == Platform.SENSOR:
        return [
            ModeSensor(router, entry),
            LastEventSensor(router, entry),
        ]
    if platform == Platform.BINARY_SENSOR:
        return [DndBinarySensor(router, entry)]
    return []


class _SubscribingEntity:
    """Mixin: connect/disconnect to the router's dispatcher signal."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, router: NotificationRouter, entry: ConfigEntry) -> None:
        self._router = router
        self._entry = entry

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_STATE_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class ModeSensor(_SubscribingEntity, SensorEntity):
    _attr_icon = "mdi:bell-cog"
    _attr_translation_key = "notification_mode"

    def __init__(self, router: NotificationRouter, entry: ConfigEntry) -> None:
        _SubscribingEntity.__init__(self, router, entry)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, SENSOR_MODE)
        self._attr_name = "Notification Mode"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str:
        d = self._router.last_decision
        return d.mode if d else MODE_SILENT

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._router.last_decision
        if not d:
            return {}
        return {
            "routes": d.routes,
            "suppressed_routes": d.suppressed_routes,
            "reason": d.reason,
            "context": d.context,
            "severity": d.severity,
            "masked": d.masked,
        }


class LastEventSensor(_SubscribingEntity, SensorEntity):
    _attr_icon = "mdi:bell-ring"
    _attr_translation_key = "last_event"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, router: NotificationRouter, entry: ConfigEntry) -> None:
        _SubscribingEntity.__init__(self, router, entry)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, SENSOR_LAST_EVENT)
        self._attr_name = "Last Notification Event"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str | None:
        ev = self._router.last_event
        return ev.event_type if ev else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ev = self._router.last_event
        d = self._router.last_decision
        if not ev:
            return {}
        return {
            "severity": ev.severity,
            "title": ev.title,
            "message": ev.message,
            "dedupe_key": ev.dedupe_key,
            "payload": ev.payload,
            "mode": d.mode if d else None,
            "routes": d.routes if d else [],
        }


class DndBinarySensor(_SubscribingEntity, BinarySensorEntity):
    _attr_icon = "mdi:bell-off"
    _attr_translation_key = "dnd_active"

    def __init__(self, router: NotificationRouter, entry: ConfigEntry) -> None:
        _SubscribingEntity.__init__(self, router, entry)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, BINARY_SENSOR_DND)
        self._attr_name = "Notification DND"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return self._router.dnd_active()
