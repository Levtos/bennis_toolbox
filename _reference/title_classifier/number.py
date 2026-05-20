"""Number entities for Entity Title Mapper watchers."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WatcherRuntime
from .const import ATTR_KEY, DOMAIN, MAX_ENUM, MIN_ENUM


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Title Classifier number entities for a watcher."""
    runtime: WatcherRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TitleClassifierCurrentTitleEnumNumber(runtime)])


class TitleClassifierCurrentTitleEnumNumber(NumberEntity):
    """Control that assigns an enum to the currently active title."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:numeric"
    _attr_mode = NumberMode.BOX
    _attr_name = "Current title enum"
    _attr_native_max_value = MAX_ENUM
    _attr_native_min_value = MIN_ENUM
    _attr_native_step = 1
    _attr_should_poll = False

    def __init__(self, runtime: WatcherRuntime) -> None:
        """Initialise the current-title enum control."""
        self._runtime = runtime
        slug = runtime.entry.data[CONF_NAME].lower().replace(" ", "_")
        self._attr_unique_id = f"{runtime.entry.entry_id}_current_title_enum"
        self.entity_id = f"number.title_classifier_{slug}_current_title_enum"
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

    @property
    def available(self) -> bool:
        """Return whether a current title can be mapped."""
        return self._runtime.current_key is not None

    @property
    def native_value(self) -> int | None:
        """Return the enum assigned to the current title."""
        return self._runtime.current_enum

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Expose the title that will be changed by this control."""
        return {ATTR_KEY: self._runtime.current_key}

    async def async_set_native_value(self, value: float) -> None:
        """Assign the selected enum to the current title."""
        enum = int(value)
        if enum != value:
            raise HomeAssistantError("Title Classifier enum must be a whole number")
        if enum < MIN_ENUM or enum > MAX_ENUM:
            raise HomeAssistantError(f"Title Classifier enum must be between {MIN_ENUM} and {MAX_ENUM}")
        await self._runtime.async_set_current_enum(enum)
