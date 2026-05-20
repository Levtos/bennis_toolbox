"""Config- und Options-Flow-Helfer für Benni Context.

Two-step Add-Flow:
  module_step (Quell-Entities) → thresholds (Radien & Zeitfenster) → Entry

Options-Flow als Menü: entities | thresholds.
Single-Instance: die Modul-Instanz hat unique_id `benni_context_singleton`.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ...const import CONF_MODULE_ID
from .const import (
    CONF_COFFEE_ACTIVE,
    CONF_DOOR_WAKE,
    CONF_GPS_PRIMARY,
    CONF_GPS_SECONDARY,
    CONF_HOLIDAY_SENSOR,
    CONF_HOMEOFFICE_PING,
    CONF_HOME_RADIUS,
    CONF_HOUSEHOLD_SOURCE,
    CONF_HYSTERESIS_M,
    CONF_MEDIA_CONTEXT,
    CONF_NEAR_RADIUS,
    CONF_PC_ACTIVE,
    CONF_PREHEAT_DURATION,
    CONF_PREHEAT_RADIUS,
    CONF_PRIVATE_SOURCE,
    CONF_PROXIMITY_DIRECTION,
    CONF_PROXIMITY_DISTANCE,
    CONF_PS5_ACTIVE,
    CONF_TRACKER_FRESHNESS,
    CONF_TRANSITION_HOLD,
    CONF_WAKE_NEEDED,
    CONF_WAKE_NEXT,
    CONF_WLAN_BENNI,
    CONF_WLAN_ELTERN_1,
    CONF_WLAN_ELTERN_2,
    DEFAULT_HOME_RADIUS,
    DEFAULT_HYSTERESIS_M,
    DEFAULT_NEAR_RADIUS,
    DEFAULT_PREHEAT_DURATION,
    DEFAULT_PREHEAT_RADIUS,
    DEFAULT_TRACKER_FRESHNESS,
    DEFAULT_TRANSITION_HOLD,
    MODULE_ID,
    NAME,
)


def _esel(domains: list[str] | None = None) -> selector.EntitySelector:
    cfg: dict[str, Any] = {"multiple": False}
    if domains:
        cfg["domain"] = domains
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


_ENTITY_SLOTS: tuple[tuple[str, list[str]], ...] = (
    (CONF_GPS_PRIMARY, ["device_tracker", "person"]),
    (CONF_GPS_SECONDARY, ["device_tracker", "person"]),
    (CONF_WLAN_BENNI, ["device_tracker"]),
    (CONF_WLAN_ELTERN_1, ["device_tracker"]),
    (CONF_WLAN_ELTERN_2, ["device_tracker"]),
    (CONF_PROXIMITY_DISTANCE, ["sensor", "proximity"]),
    (CONF_PROXIMITY_DIRECTION, ["sensor", "proximity"]),
    # NB: wake_next / wake_needed werden hier nur als HA-Entities konfiguriert;
    # die Logik dahinter liegt im Wake-Planner-Modul. Benni Context
    # konsumiert sie als Inputs, ohne Wake-Planner-Code zu importieren.
    (CONF_WAKE_NEXT, ["sensor", "input_datetime"]),
    (CONF_WAKE_NEEDED, ["binary_sensor", "input_boolean"]),
    (CONF_PC_ACTIVE, ["binary_sensor", "switch", "input_boolean"]),
    (CONF_PS5_ACTIVE, ["binary_sensor", "switch", "input_boolean"]),
    (CONF_COFFEE_ACTIVE, ["binary_sensor", "switch", "input_boolean"]),
    (CONF_DOOR_WAKE, ["binary_sensor", "input_boolean"]),
    (CONF_MEDIA_CONTEXT, ["sensor", "input_select"]),
    (CONF_PRIVATE_SOURCE, ["binary_sensor", "input_boolean"]),
    (CONF_HOMEOFFICE_PING, ["binary_sensor", "input_boolean"]),
    (CONF_HOLIDAY_SENSOR, ["binary_sensor", "calendar", "input_boolean"]),
    (CONF_HOUSEHOLD_SOURCE, ["binary_sensor", "input_boolean"]),
)


def _entities_schema(defaults: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {}
    for key, domains in _ENTITY_SLOTS:
        d = defaults.get(key)
        marker = vol.Optional(key, default=d) if d else vol.Optional(key)
        fields[marker] = _esel(domains)
    return vol.Schema(fields)


def _thresholds_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_HOME_RADIUS, default=defaults.get(CONF_HOME_RADIUS, DEFAULT_HOME_RADIUS)):
            vol.All(vol.Coerce(int), vol.Range(min=10, max=5000)),
        vol.Required(CONF_PREHEAT_RADIUS, default=defaults.get(CONF_PREHEAT_RADIUS, DEFAULT_PREHEAT_RADIUS)):
            vol.All(vol.Coerce(int), vol.Range(min=50, max=20000)),
        vol.Required(CONF_NEAR_RADIUS, default=defaults.get(CONF_NEAR_RADIUS, DEFAULT_NEAR_RADIUS)):
            vol.All(vol.Coerce(int), vol.Range(min=200, max=100000)),
        vol.Required(CONF_HYSTERESIS_M, default=defaults.get(CONF_HYSTERESIS_M, DEFAULT_HYSTERESIS_M)):
            vol.All(vol.Coerce(int), vol.Range(min=0, max=2000)),
        vol.Required(CONF_PREHEAT_DURATION, default=defaults.get(CONF_PREHEAT_DURATION, DEFAULT_PREHEAT_DURATION)):
            vol.All(vol.Coerce(int), vol.Range(min=60, max=7200)),
        vol.Required(CONF_TRACKER_FRESHNESS, default=defaults.get(CONF_TRACKER_FRESHNESS, DEFAULT_TRACKER_FRESHNESS)):
            vol.All(vol.Coerce(int), vol.Range(min=60, max=86400)),
        vol.Required(CONF_TRANSITION_HOLD, default=defaults.get(CONF_TRANSITION_HOLD, DEFAULT_TRANSITION_HOLD)):
            vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
    })


# ---------------------------------------------------------------------------
# ConfigFlowHelper
# ---------------------------------------------------------------------------


class ConfigFlowHelper:
    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow
        self._entities: dict[str, Any] = {}

    async def async_step_init(self) -> FlowResult:
        # Single-instance gate: nur eine benni_context-Instanz erlaubt.
        await self.flow.async_set_unique_id(f"{MODULE_ID}_singleton")
        self.flow._abort_if_unique_id_configured()
        return self.flow.async_show_form(
            step_id="module_step", data_schema=_entities_schema({}),
        )

    async def async_step_module_step(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="module_step", data_schema=_entities_schema({}),
            )
        self._entities = {k: v for k, v in user_input.items() if v}
        return self.flow.async_show_form(
            step_id="thresholds", data_schema=_thresholds_schema({}),
        )

    async def async_step_thresholds(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="thresholds", data_schema=_thresholds_schema({}),
            )
        data = {CONF_MODULE_ID: MODULE_ID, **self._entities}
        return self.flow.async_create_entry(title=NAME, data=data, options=user_input)


# ---------------------------------------------------------------------------
# OptionsFlowHelper
# ---------------------------------------------------------------------------


class OptionsFlowHelper:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.flow.async_show_menu(
            step_id="init", menu_options=["entities", "thresholds"],
        )

    async def async_step_entities(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            new_data = {**self.entry.data, **{k: v for k, v in user_input.items() if v}}
            for k in list(new_data):
                if k in user_input and not user_input[k]:
                    new_data.pop(k, None)
            new_data[CONF_MODULE_ID] = MODULE_ID
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.flow.async_create_entry(title="", data=self.entry.options)
        return self.flow.async_show_form(
            step_id="entities", data_schema=_entities_schema(self.entry.data),
        )

    async def async_step_thresholds(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.flow.async_create_entry(title="", data=user_input)
        return self.flow.async_show_form(
            step_id="thresholds", data_schema=_thresholds_schema(self.entry.options),
        )
