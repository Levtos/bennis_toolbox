"""SensorEntities für Benni Core · Devices.

Pro Device-Instanz:
- Haupt-Sensor `sensor.benni_device_<slug>` (immer)
- Optional Sekundär-Sensoren bei `expose_secondary_sensors=true`:
  - `sensor.benni_device_<slug>_power_state`
  - `sensor.benni_device_<slug>_watt`  (nur wenn watt_sensor konfiguriert)

binary_sensor.py liefert die boolean-Sekundär-Sensoren (powered/available).
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import DOMAIN, unique_id
from .const import (
    CONF_DISPLAY_NAME,
    CONF_GROUP_MEMBERS,
    CONF_LIGHT_GROUPS,
    GROUP_OBJECT_ID_PREFIX,
    MODULE_ID,
    POWER_STATE_SLUGS,
)
from .coordinator import DeviceCoordinator, coordinators_for_entry
from .logic import DeviceResult


def _object_id(slug: str, suffix: str | None = None) -> str:
    base = f"benni_device_{slug}"
    return f"{base}_{suffix}" if suffix else base


def _device_info(coordinator: DeviceCoordinator) -> DeviceInfo:
    """Ein HA-Device pro Gerät, eingehängt unter dem Hub-Gerät (via_device),
    sodass alle Geräte unter 'Benni Core · Devices' gruppiert erscheinen."""
    from . import HUB_IDENTIFIER

    return DeviceInfo(
        identifiers={(DOMAIN, f"{MODULE_ID}:{coordinator.slug}")},
        name=coordinator.display_name,
        manufacturer="Benni Core · Devices",
        model=coordinator.device_type.value,
        via_device=HUB_IDENTIFIER,
    )


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: str
) -> list[Entity]:
    if platform != Platform.SENSOR:
        return []
    out: list[Entity] = []
    for coordinator in coordinators_for_entry(hass, entry).values():
        out.append(DeviceMainSensor(coordinator, entry))
        if coordinator.expose_secondary_sensors:
            out.append(PowerStateSensor(coordinator, entry))
            if coordinator.watt_slot_key:
                out.append(WattSensor(coordinator, entry))
    # Atomic Light Groups (Mengen von Lampen) — ein Sensor je Gruppe.
    groups = entry.options.get(CONF_LIGHT_GROUPS)
    if isinstance(groups, dict):
        for slug, conf in groups.items():
            members = [m for m in (conf.get(CONF_GROUP_MEMBERS) or []) if isinstance(m, str)]
            out.append(
                LightGroupSensor(
                    hass, entry, slug,
                    name=conf.get(CONF_DISPLAY_NAME, slug),
                    members=members,
                )
            )
    return out


class _BaseDeviceSensor(CoordinatorEntity[DeviceCoordinator], SensorEntity):
    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: DeviceCoordinator,
        entry: ConfigEntry,
        *,
        suffix: str,
        object_id: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, suffix)
        self._attr_name = name
        self._attr_device_info = _device_info(coordinator)
        # Entity-ID deterministisch erzwingen (sonst leitet HA sie aus dem
        # Anzeigenamen ab → sensor.tv). Wir wollen sensor.benni_device_<slug>.
        self.entity_id = async_generate_entity_id(
            "sensor.{}", object_id, hass=coordinator.hass
        )

    @property
    def _result(self) -> DeviceResult | None:
        return self.coordinator.data


class DeviceMainSensor(_BaseDeviceSensor):
    """Der EINE konsolidierte Sensor pro Device."""

    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: DeviceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            suffix=f"{coordinator.slug}_main",
            object_id=_object_id(coordinator.slug),
            name=coordinator.display_name,
        )

    @property
    def native_value(self) -> str | None:
        r = self._result
        return r.state if r else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self._result
        if r is None:
            return {}
        c = self.coordinator
        attrs: dict[str, Any] = {
            "device_type": c.device_type.value,
            "slug": c.slug,
            "display_name": c.display_name,
            "powered": r.powered,
            "power_state": r.power_state,
            "available": r.available,
            "power_source": r.power_source,
            "last_powered_change": r.last_powered_change,
            "override_active": r.override_active,
            "watt_disagrees": r.watt_disagrees,
            "area_id": c._derive_area_id(),
        }
        # Typspezifische Extra-Attribute (LH §6)
        from .device_types import profile_for

        profile = profile_for(c.device_type)
        for key in profile.extra_attributes:
            if key == "watt":
                attrs[key] = r.watt
            elif key in ("media_player_state", "hvac_mode"):
                # State des state_slots (media_player-State bzw. climate hvac_mode)
                attrs[key] = r.raw_state if profile.state_slot else None
            elif key == "target_temperature":
                # HA-climate trägt den Sollwert im Attribut "temperature"
                attrs[key] = r.extra.get("temperature")
            else:
                attrs[key] = r.extra.get(key)
        return attrs


class PowerStateSensor(_BaseDeviceSensor):
    """Optionaler Sekundär-Sensor: aus Watt-Buckets abgeleiteter power_state."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(POWER_STATE_SLUGS)
    _attr_icon = "mdi:flash"

    def __init__(self, coordinator: DeviceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            suffix=f"{coordinator.slug}_power_state",
            object_id=_object_id(coordinator.slug, "power_state"),
            name=f"{coordinator.display_name} Power State",
        )

    @property
    def native_value(self) -> str | None:
        r = self._result
        return r.power_state if r else None


class LightGroupSensor(SensorEntity):
    """Atomic Light Group: eine Menge von Lampen als EINE Wahrheit.

    State = "on" wenn mind. eine Member-Lampe an ist, sonst "off".
    Attribute exponieren die Member (`members` + HA-Group-Style `entity_id`),
    damit Konsumenten (z.B. light_policy) sie auf die Einzellampen expandieren
    können (Scene-Presets verteilt Paletten über Einzel-Member).
    """

    _attr_should_poll = False
    _attr_has_entity_name = False
    _attr_icon = "mdi:lightbulb-group"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        slug: str,
        *,
        name: str,
        members: list[str],
    ) -> None:
        from . import GROUPS_HUB_IDENTIFIER

        self._members = list(members)
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, f"group_{slug}")
        self._attr_name = name
        self._attr_device_info = DeviceInfo(identifiers={GROUPS_HUB_IDENTIFIER})
        self.entity_id = async_generate_entity_id(
            "sensor.{}", f"{GROUP_OBJECT_ID_PREFIX}{slug}", hass=hass
        )
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        if self._members:
            self._unsub = async_track_state_change_event(
                self.hass, self._members, self._on_member_change
            )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def _on_member_change(self, _event) -> None:
        self.async_write_ha_state()

    def _on_members(self) -> list[str]:
        return [
            m for m in self._members
            if (st := self.hass.states.get(m)) is not None and st.state == "on"
        ]

    @property
    def native_value(self) -> str:
        return "on" if self._on_members() else "off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        on = self._on_members()
        return {
            "members": list(self._members),
            "entity_id": list(self._members),  # HA-Group-Style für Konsumenten
            "member_count": len(self._members),
            "on_count": len(on),
            "any_on": bool(on),
        }


class WattSensor(_BaseDeviceSensor):
    """Optionaler Sekundär-Sensor: numerischer Watt-Wert."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "W"
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator: DeviceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            suffix=f"{coordinator.slug}_watt",
            object_id=_object_id(coordinator.slug, "watt"),
            name=f"{coordinator.display_name} Watt",
        )

    @property
    def native_value(self) -> float | None:
        r = self._result
        return r.watt if r else None
