"""Sensor entities."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, MODE_SILENT, SENSOR_LAST_EVENT, SENSOR_MODE
from .coordinator import SIGNAL_STATE_UPDATED, NotificationRouter


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    router: NotificationRouter = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        BenniModeSensor(router, entry.entry_id),
        BenniLastEventSensor(router, entry.entry_id),
    ])


class _RouterEntity(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, router: NotificationRouter, entry_id: str) -> None:
        self._router = router
        self._entry_id = entry_id

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_STATE_UPDATED, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class BenniModeSensor(_RouterEntity):
    _attr_translation_key = "notification_mode"
    _attr_icon = "mdi:bell-cog"

    def __init__(self, router: NotificationRouter, entry_id: str) -> None:
        super().__init__(router, entry_id)
        self._attr_unique_id = f"{entry_id}_{SENSOR_MODE}"
        self._attr_name = "Benni Notification Mode"

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


class BenniLastEventSensor(_RouterEntity):
    _attr_translation_key = "last_event"
    _attr_icon = "mdi:bell-ring"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, router: NotificationRouter, entry_id: str) -> None:
        super().__init__(router, entry_id)
        self._attr_unique_id = f"{entry_id}_{SENSOR_LAST_EVENT}"
        self._attr_name = "Benni Last Notification Event"

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
