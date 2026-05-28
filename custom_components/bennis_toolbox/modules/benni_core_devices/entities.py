"""Entity-Lookup-Dispatcher gemäß ModuleProtocol.

Wir haben zwei Plattformen (sensor + binary_sensor) — dispatch by platform.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: str
) -> list[Entity]:
    if platform == Platform.SENSOR:
        from .sensor import async_get_entities as _sensor

        return await _sensor(hass, entry, platform)
    if platform == Platform.BINARY_SENSOR:
        from .binary_sensor import async_get_entities as _binary

        return await _binary(hass, entry, platform)
    return []


__all__ = ["async_get_entities"]
