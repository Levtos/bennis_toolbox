"""Sensor entities for Entity Title Mapper watchers."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from . import WatcherRuntime
from .const import ATTR_KEY, ATTR_WATCHER_ID, ATTR_WATCHER_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Title Classifier sensors for a watcher."""
    runtime: WatcherRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TitleClassifierEnumSensor(runtime), TitleClassifierRawSensor(runtime), TitleClassifierCatalogSensor(runtime)])


class TitleClassifierBaseSensor(SensorEntity):
    """Base sensor for Title Classifier watcher outputs."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, runtime: WatcherRuntime) -> None:
        """Initialise the sensor."""
        self._runtime = runtime
        self._attr_device_info = {
            "identifiers": {(DOMAIN, runtime.entry.entry_id)},
            "name": runtime.entry.data[CONF_NAME],
            "manufacturer": "Entity Title Mapper",
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime updates."""
        self._runtime.add_listener(self._handle_runtime_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from runtime updates."""
        self._runtime.remove_listener(self._handle_runtime_update)

    @callback
    def _handle_runtime_update(self) -> None:
        """Refresh HA state from runtime state."""
        self.async_write_ha_state()


class TitleClassifierEnumSensor(TitleClassifierBaseSensor):
    """Sensor exposing the mapped enum value."""

    _attr_name = "Enum"
    _attr_icon = "mdi:numeric"
    _attr_native_unit_of_measurement = None

    def __init__(self, runtime: WatcherRuntime) -> None:
        """Initialise the enum sensor."""
        super().__init__(runtime)
        slug = runtime.entry.data[CONF_NAME].lower().replace(" ", "_")
        self._attr_unique_id = f"{runtime.entry.entry_id}_enum"
        self.entity_id = f"sensor.title_classifier_{slug}_enum"

    @property
    def native_value(self) -> int | None:
        """Return the current enum."""
        return self._runtime.current_enum

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return slim attributes safe for recorder storage."""
        return {
            ATTR_KEY: self._runtime.current_key,
            ATTR_WATCHER_ID: self._runtime.entry.entry_id,
            ATTR_WATCHER_NAME: self._runtime.name,
            "entry_count": self._runtime.catalog_summary()["entry_count"],
        }


class TitleClassifierRawSensor(TitleClassifierBaseSensor):
    """Sensor exposing the current raw key string."""

    _attr_name = "Raw"
    _attr_icon = "mdi:form-textbox"

    def __init__(self, runtime: WatcherRuntime) -> None:
        """Initialise the raw sensor."""
        super().__init__(runtime)
        slug = runtime.entry.data[CONF_NAME].lower().replace(" ", "_")
        self._attr_unique_id = f"{runtime.entry.entry_id}_raw"
        self.entity_id = f"sensor.title_classifier_{slug}_raw"

    @property
    def native_value(self) -> str | None:
        """Return the current raw key."""
        return self._runtime.current_key

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return slim attributes safe for recorder storage."""
        return {
            ATTR_KEY: self._runtime.current_key,
            ATTR_WATCHER_ID: self._runtime.entry.entry_id,
            ATTR_WATCHER_NAME: self._runtime.name,
            "entry_count": self._runtime.catalog_summary()["entry_count"],
        }


class TitleClassifierCatalogSensor(TitleClassifierBaseSensor):
    """Diagnostic sensor exposing the stored title catalog for a watcher."""

    _attr_name = "Catalog"
    _attr_icon = "mdi:database-search"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: WatcherRuntime) -> None:
        """Initialise the catalog sensor."""
        super().__init__(runtime)
        slug = runtime.entry.data[CONF_NAME].lower().replace(" ", "_")
        self._attr_unique_id = f"{runtime.entry.entry_id}_catalog"
        self.entity_id = f"sensor.title_classifier_{slug}_catalog"

    @property
    def native_value(self) -> int:
        """Return the number of tracked title entries."""
        return self._runtime.catalog_summary()["entry_count"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return catalog counts — full lists are omitted to stay within recorder limits."""
        entries = self._runtime.store.entries
        total = len(entries)
        mapped = sum(1 for e in entries.values() if e.enum != 0)
        return {
            ATTR_KEY: self._runtime.current_key,
            ATTR_WATCHER_ID: self._runtime.entry.entry_id,
            ATTR_WATCHER_NAME: self._runtime.name,
            "entry_count": total,
            "mapped_count": mapped,
            "unmapped_count": total - mapped,
        }
