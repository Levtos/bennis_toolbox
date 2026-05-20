"""Binary sensor entities."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import BINARY_SENSOR_DND, DOMAIN
from .coordinator import SIGNAL_STATE_UPDATED, NotificationRouter


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    router: NotificationRouter = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BenniDndBinarySensor(router, entry.entry_id)])


class BenniDndBinarySensor(BinarySensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:bell-off"
    _attr_translation_key = "dnd_active"

    def __init__(self, router: NotificationRouter, entry_id: str) -> None:
        self._router = router
        self._attr_unique_id = f"{entry_id}_{BINARY_SENSOR_DND}"
        self._attr_name = "Benni Notification DND"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_STATE_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._router.dnd_active()
