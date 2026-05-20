"""button platform dispatcher — delegiert pro Config-Entry an das jeweilige Toolbox-Modul."""
from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ._platform_dispatch import async_setup_platform_for


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    await async_setup_platform_for(hass, entry, async_add_entities, Platform.BUTTON)
