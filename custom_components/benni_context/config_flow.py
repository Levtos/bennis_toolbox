"""Config and Options flow for Benni Context."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_COFFEE_ACTIVE,
    CONF_DOOR_WAKE,
    CONF_GPS_PRIMARY,
    CONF_GPS_SECONDARY,
    CONF_HOLIDAY_SENSOR,
    CONF_HOME_RADIUS,
    CONF_HOMEOFFICE_PING,
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
    DOMAIN,
)


def _entity_selector(domains: list[str] | None = None) -> selector.EntitySelector:
    cfg: dict[str, Any] = {"multiple": False}
    if domains:
        cfg["domain"] = domains
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


def _entities_schema(defaults: dict[str, Any]) -> vol.Schema:
    def _opt(key: str, sel: selector.EntitySelector) -> Any:
        d = defaults.get(key)
        if d:
            return vol.Optional(key, default=d)
        return vol.Optional(key)

    return vol.Schema(
        {
            _opt(CONF_GPS_PRIMARY, _entity_selector(["device_tracker", "person"])):
                _entity_selector(["device_tracker", "person"]),
            _opt(CONF_GPS_SECONDARY, _entity_selector(["device_tracker", "person"])):
                _entity_selector(["device_tracker", "person"]),
            _opt(CONF_WLAN_BENNI, _entity_selector(["device_tracker"])):
                _entity_selector(["device_tracker"]),
            _opt(CONF_WLAN_ELTERN_1, _entity_selector(["device_tracker"])):
                _entity_selector(["device_tracker"]),
            _opt(CONF_WLAN_ELTERN_2, _entity_selector(["device_tracker"])):
                _entity_selector(["device_tracker"]),
            _opt(CONF_PROXIMITY_DISTANCE, _entity_selector(["sensor", "proximity"])):
                _entity_selector(["sensor", "proximity"]),
            _opt(CONF_PROXIMITY_DIRECTION, _entity_selector(["sensor", "proximity"])):
                _entity_selector(["sensor", "proximity"]),
            _opt(CONF_WAKE_NEXT, _entity_selector(["sensor", "input_datetime"])):
                _entity_selector(["sensor", "input_datetime"]),
            _opt(CONF_WAKE_NEEDED, _entity_selector(["binary_sensor", "input_boolean"])):
                _entity_selector(["binary_sensor", "input_boolean"]),
            _opt(CONF_PC_ACTIVE, _entity_selector(["binary_sensor", "switch", "input_boolean"])):
                _entity_selector(["binary_sensor", "switch", "input_boolean"]),
            _opt(CONF_PS5_ACTIVE, _entity_selector(["binary_sensor", "switch", "input_boolean"])):
                _entity_selector(["binary_sensor", "switch", "input_boolean"]),
            _opt(CONF_COFFEE_ACTIVE, _entity_selector(["binary_sensor", "switch", "input_boolean"])):
                _entity_selector(["binary_sensor", "switch", "input_boolean"]),
            _opt(CONF_DOOR_WAKE, _entity_selector(["binary_sensor", "input_boolean"])):
                _entity_selector(["binary_sensor", "input_boolean"]),
            _opt(CONF_MEDIA_CONTEXT, _entity_selector(["sensor", "input_select"])):
                _entity_selector(["sensor", "input_select"]),
            _opt(CONF_PRIVATE_SOURCE, _entity_selector(["binary_sensor", "input_boolean"])):
                _entity_selector(["binary_sensor", "input_boolean"]),
            _opt(CONF_HOMEOFFICE_PING, _entity_selector(["binary_sensor", "input_boolean"])):
                _entity_selector(["binary_sensor", "input_boolean"]),
            _opt(CONF_HOLIDAY_SENSOR, _entity_selector(["binary_sensor", "calendar", "input_boolean"])):
                _entity_selector(["binary_sensor", "calendar", "input_boolean"]),
            _opt(CONF_HOUSEHOLD_SOURCE, _entity_selector(["binary_sensor", "input_boolean"])):
                _entity_selector(["binary_sensor", "input_boolean"]),
        }
    )


def _thresholds_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_HOME_RADIUS,
                default=defaults.get(CONF_HOME_RADIUS, DEFAULT_HOME_RADIUS),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=5000)),
            vol.Required(
                CONF_PREHEAT_RADIUS,
                default=defaults.get(CONF_PREHEAT_RADIUS, DEFAULT_PREHEAT_RADIUS),
            ): vol.All(vol.Coerce(int), vol.Range(min=50, max=20000)),
            vol.Required(
                CONF_NEAR_RADIUS,
                default=defaults.get(CONF_NEAR_RADIUS, DEFAULT_NEAR_RADIUS),
            ): vol.All(vol.Coerce(int), vol.Range(min=200, max=100000)),
            vol.Required(
                CONF_HYSTERESIS_M,
                default=defaults.get(CONF_HYSTERESIS_M, DEFAULT_HYSTERESIS_M),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=2000)),
            vol.Required(
                CONF_PREHEAT_DURATION,
                default=defaults.get(CONF_PREHEAT_DURATION, DEFAULT_PREHEAT_DURATION),
            ): vol.All(vol.Coerce(int), vol.Range(min=60, max=7200)),
            vol.Required(
                CONF_TRACKER_FRESHNESS,
                default=defaults.get(CONF_TRACKER_FRESHNESS, DEFAULT_TRACKER_FRESHNESS),
            ): vol.All(vol.Coerce(int), vol.Range(min=60, max=86400)),
            vol.Required(
                CONF_TRANSITION_HOLD,
                default=defaults.get(CONF_TRANSITION_HOLD, DEFAULT_TRANSITION_HOLD),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
        }
    )


class BenniContextConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial config flow — single instance only."""

    VERSION = 1

    def __init__(self) -> None:
        self._entities: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            self._entities = {k: v for k, v in user_input.items() if v}
            return await self.async_step_thresholds()

        return self.async_show_form(
            step_id="user",
            data_schema=_entities_schema({}),
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Benni Context",
                data=self._entities,
                options=user_input,
            )
        return self.async_show_form(
            step_id="thresholds",
            data_schema=_thresholds_schema({}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BenniContextOptionsFlow(config_entry)


class BenniContextOptionsFlow(OptionsFlow):
    """Edit entities and thresholds after install."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._entities: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["entities", "thresholds"],
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            new_data = {**self.entry.data, **{k: v for k, v in user_input.items() if v}}
            # remove keys that were cleared
            for k in list(new_data):
                if k in user_input and not user_input[k]:
                    new_data.pop(k, None)
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.async_create_entry(title="", data=self.entry.options)
        return self.async_show_form(
            step_id="entities",
            data_schema=_entities_schema(self.entry.data),
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="thresholds",
            data_schema=_thresholds_schema(self.entry.options),
        )
