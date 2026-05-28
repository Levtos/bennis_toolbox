"""DataUpdateCoordinator für Benni Core · Devices.

Pro Device-Instanz ein Coordinator:
- liest alle konfigurierten Slot-Entities
- bridge HA-State → SlotReading
- ruft pure logic.compute_device()
- persistiert last_powered + Override über HA-Restarts
- registriert Service-Override / Clear via services_impl

Boot-Phase (R-DC-09): Coordinator merkt sich Start-Zeitpunkt;
logic.is_boot_phase() entscheidet ob Sticky-Hold greift.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.area_registry import async_get as async_get_areas
from homeassistant.helpers.entity_registry import async_get as async_get_entities
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from ...const import DATA_ENTRIES, DOMAIN
from ...storage import make_store
from . import logic
from .const import (
    CONF_DEVICE_TYPE,
    CONF_DISPLAY_NAME,
    CONF_EXPOSE_SECONDARY_SENSORS,
    CONF_SLUG,
    CONF_STICKY_HOLD_SECONDS,
    CONF_WATT_BUCKETS,
    CONF_WATT_THRESHOLD_ON,
    DEFAULT_EXPOSE_SECONDARY_SENSORS,
    DEFAULT_STICKY_HOLD_SECONDS,
    DEFAULT_WATT_THRESHOLD_ON,
    MODULE_ID,
    STORAGE_KEY_LAST_POWERED,
    STORAGE_KEY_LAST_POWERED_CHANGE,
    STORAGE_KEY_OVERRIDE,
    STORAGE_KEY_OVERRIDE_EXPIRES_AT,
    STORAGE_KEY_OVERRIDE_POWER_STATE,
    STORAGE_KEY_OVERRIDE_POWERED,
    STORAGE_VERSION,
    UPDATE_INTERVAL_SECONDS,
    DeviceType,
)
from .device_types import ALL_SLOT_KEYS, DeviceTypeProfile, profile_for
from .logic import (
    DeviceConfig,
    DeviceInputs,
    DevicePersisted,
    DeviceResult,
    Override,
    SlotReading,
)

_LOGGER = logging.getLogger(__name__)


class DeviceCoordinator(DataUpdateCoordinator[DeviceResult]):
    """Treibt einen Device-Sensor."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{MODULE_ID}_{entry.entry_id}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.entry = entry
        self._store = make_store(
            hass, MODULE_ID, f"state_{entry.entry_id}", version=STORAGE_VERSION
        )
        self._persisted = DevicePersisted(
            last_powered=None,
            last_powered_change=None,
            override=None,
        )
        self._unsub_listeners: list[CALLBACK_TYPE] = []
        self._boot_start: datetime = dt_util.now()
        self._profile: DeviceTypeProfile = profile_for(self.device_type)

    # ─────────────────────────────────────────────────────── Config Access

    def _opt(self, key: str, default: Any = None) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def slug(self) -> str:
        return str(self.entry.data[CONF_SLUG])

    @property
    def display_name(self) -> str:
        return str(self.entry.data.get(CONF_DISPLAY_NAME) or self.slug)

    @property
    def device_type(self) -> DeviceType:
        return DeviceType(self.entry.data[CONF_DEVICE_TYPE])

    @property
    def watt_threshold_on(self) -> int:
        return int(self._opt(CONF_WATT_THRESHOLD_ON, DEFAULT_WATT_THRESHOLD_ON))

    @property
    def sticky_hold_seconds(self) -> int:
        return int(self._opt(CONF_STICKY_HOLD_SECONDS, DEFAULT_STICKY_HOLD_SECONDS))

    @property
    def expose_secondary_sensors(self) -> bool:
        return bool(self._opt(CONF_EXPOSE_SECONDARY_SENSORS, DEFAULT_EXPOSE_SECONDARY_SENSORS))

    @property
    def configured_slot_entities(self) -> dict[str, str]:
        """Slot-Key → Entity-ID, nur tatsächlich konfigurierte.

        Iteriert über den globalen Slot-Katalog (Felder sind user-gewählt,
        nicht typ-fix), nicht mehr über typ-spezifische Profil-Slots.
        """
        out: dict[str, str] = {}
        for key in ALL_SLOT_KEYS:
            eid = self.entry.data.get(key)
            if eid:
                out[key] = str(eid)
        return out

    @property
    def watt_slot_key(self) -> str | None:
        """Welcher Slot-Key liefert den Watt-Sensor (für power_state R-DC-06)?"""
        from .const import CONF_WATT_SENSOR

        if CONF_WATT_SENSOR in self.configured_slot_entities:
            return CONF_WATT_SENSOR
        return None

    # ─────────────────────────────────────────────────────── Storage

    async def async_load_stored(self) -> None:
        raw = await self._store.async_load()
        if raw is None:
            return
        self._persisted = _persisted_from_dict(raw)

    async def _async_save(self) -> None:
        await self._store.async_save(_persisted_to_dict(self._persisted))

    # ─────────────────────────────────────────────────────── Lifecycle

    def async_start_listeners(self) -> None:
        watched = list(self.configured_slot_entities.values())
        if watched:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass, watched, self._async_on_slot_change
                )
            )

    def async_stop_listeners(self) -> None:
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    # ─────────────────────────────────────────────────────── Event-Handler

    @callback
    def _async_on_slot_change(self, _event: Event) -> None:
        self.hass.async_create_task(self._async_recompute_and_persist())

    async def _async_recompute_and_persist(self) -> None:
        result = self._compute()
        await self._persist_if_changed(result)
        self.async_set_updated_data(result)

    # ─────────────────────────────────────────────────────── Service-Hooks

    async def async_set_override(
        self,
        powered: bool | None,
        power_state: str | None,
        expire_seconds: int | None,
    ) -> DeviceResult:
        """R-DC-07: Override aktivieren."""
        now = dt_util.now()
        override = logic.build_override(powered, power_state, expire_seconds, now)
        self._persisted = DevicePersisted(
            last_powered=self._persisted.last_powered,
            last_powered_change=self._persisted.last_powered_change,
            override=override,
        )
        await self._async_save()
        result = self._compute()
        self.async_set_updated_data(result)
        return result

    async def async_clear_override(self) -> DeviceResult:
        """R-DC-07: Override entfernen."""
        self._persisted = DevicePersisted(
            last_powered=self._persisted.last_powered,
            last_powered_change=self._persisted.last_powered_change,
            override=None,
        )
        await self._async_save()
        result = self._compute()
        self.async_set_updated_data(result)
        return result

    # ─────────────────────────────────────────────────────── Compute

    async def _async_update_data(self) -> DeviceResult:
        return self._compute()

    def _compute(self) -> DeviceResult:
        now = dt_util.now()
        inputs = self._read_inputs(now)
        config = self._build_config()
        result = logic.compute_device(config, inputs, self._persisted, now)

        # Override-Expiry-Check: wenn aktiver Override gerade abgelaufen ist,
        # räume ihn auf (in Storage). Kein Race weil _persist_if_changed
        # sowieso wieder gesaved wird.
        if (
            self._persisted.override is not None
            and logic.is_override_expired(self._persisted.override, now)
        ):
            self._persisted = DevicePersisted(
                last_powered=self._persisted.last_powered,
                last_powered_change=self._persisted.last_powered_change,
                override=None,
            )

        return result

    async def _persist_if_changed(self, result: DeviceResult) -> None:
        if (
            result.powered == self._persisted.last_powered
            and result.last_powered_change == self._persisted.last_powered_change
        ):
            return
        self._persisted = DevicePersisted(
            last_powered=result.powered,
            last_powered_change=result.last_powered_change,
            override=self._persisted.override,
        )
        await self._async_save()

    def _build_config(self) -> DeviceConfig:
        return DeviceConfig(
            slug=self.slug,
            display_name=self.display_name,
            device_type=self.device_type.value,
            watt_threshold_on=self.watt_threshold_on,
            watt_buckets=logic.parse_watt_buckets(self._opt(CONF_WATT_BUCKETS)),
            sticky_hold_seconds=self.sticky_hold_seconds,
            area_id=self._derive_area_id(),
            configured_slots=tuple(self.configured_slot_entities.keys()),
        )

    def _derive_area_id(self) -> str | None:
        """area_id aus HA-Area-Registry der Pflicht-Slot-Entity (OQ-5)."""
        slot_key = self._profile.integration_slot
        if not slot_key:
            return None
        eid = self.configured_slot_entities.get(slot_key)
        if not eid:
            return None
        ent_reg = async_get_entities(self.hass)
        entry = ent_reg.async_get(eid)
        if entry is None:
            return None
        # area_id kann direkt am Entity oder am Device hängen
        if entry.area_id:
            return entry.area_id
        if entry.device_id:
            from homeassistant.helpers.device_registry import async_get as async_get_devs

            dev_reg = async_get_devs(self.hass)
            dev = dev_reg.async_get(entry.device_id)
            if dev and dev.area_id:
                return dev.area_id
        return None

    def _read_inputs(self, now: datetime) -> DeviceInputs:
        slots: dict[str, SlotReading] = {}
        for slot_key, entity_id in self.configured_slot_entities.items():
            slots[slot_key] = self._read_slot(entity_id)
        return DeviceInputs(
            slots=slots,
            integration_slot=self._profile.integration_slot,
            state_slot=self._profile.state_slot,
            watt_slot=self.watt_slot_key,
            boot_phase_active=logic.is_boot_phase(self._boot_start, now),
        )

    def _read_slot(self, entity_id: str) -> SlotReading:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
            return SlotReading(value=None)
        numeric: float | None = None
        try:
            numeric = float(state.state)
        except (TypeError, ValueError):
            numeric = None
        return SlotReading(
            value=state.state,
            numeric=numeric,
            attributes=dict(state.attributes),
            last_updated=state.last_updated,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Lookup-Helper
# ─────────────────────────────────────────────────────────────────────────────


@callback
def coordinator_from_hass(
    hass: HomeAssistant, entry: ConfigEntry
) -> DeviceCoordinator | None:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    if not bucket:
        return None
    return bucket.get("coordinator")


@callback
def all_coordinators(hass: HomeAssistant) -> list[DeviceCoordinator]:
    """Alle Device-Coordinators (für Service-Resolution by-slug)."""
    out: list[DeviceCoordinator] = []
    for bucket in hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).values():
        c = bucket.get("coordinator")
        if isinstance(c, DeviceCoordinator):
            out.append(c)
    return out


@callback
def coordinator_by_slug(hass: HomeAssistant, slug: str) -> DeviceCoordinator | None:
    for c in all_coordinators(hass):
        if c.slug == slug:
            return c
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Persistenz-Codec
# ─────────────────────────────────────────────────────────────────────────────


def _persisted_to_dict(p: DevicePersisted) -> dict[str, Any]:
    out: dict[str, Any] = {
        STORAGE_KEY_LAST_POWERED: p.last_powered,
        STORAGE_KEY_LAST_POWERED_CHANGE: (
            p.last_powered_change.isoformat() if p.last_powered_change else None
        ),
        STORAGE_KEY_OVERRIDE: None,
    }
    if p.override is not None:
        out[STORAGE_KEY_OVERRIDE] = {
            STORAGE_KEY_OVERRIDE_POWERED: p.override.powered,
            STORAGE_KEY_OVERRIDE_POWER_STATE: p.override.power_state,
            STORAGE_KEY_OVERRIDE_EXPIRES_AT: (
                p.override.expires_at.isoformat() if p.override.expires_at else None
            ),
        }
    return out


def _persisted_from_dict(raw: dict[str, Any]) -> DevicePersisted:
    override_raw = raw.get(STORAGE_KEY_OVERRIDE)
    override: Override | None = None
    if isinstance(override_raw, dict):
        override = Override(
            powered=override_raw.get(STORAGE_KEY_OVERRIDE_POWERED),
            power_state=override_raw.get(STORAGE_KEY_OVERRIDE_POWER_STATE),
            expires_at=_parse_iso(
                override_raw.get(STORAGE_KEY_OVERRIDE_EXPIRES_AT)
            ),
        )
    return DevicePersisted(
        last_powered=raw.get(STORAGE_KEY_LAST_POWERED),
        last_powered_change=_parse_iso(raw.get(STORAGE_KEY_LAST_POWERED_CHANGE)),
        override=override,
    )


def _parse_iso(v: Any) -> datetime | None:
    if not isinstance(v, str) or not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None
