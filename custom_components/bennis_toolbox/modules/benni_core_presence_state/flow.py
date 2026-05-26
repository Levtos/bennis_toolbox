"""Config- und Options-Flow-Helfer für Benni Core · Presence State.

Single-Instance.
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
    CONF_HOME_RADIUS_M,
    CONF_HYSTERESIS_M,
    CONF_ICLOUD_TRACKER,
    CONF_MOBILE_TRACKER,
    CONF_NEAR_RADIUS_M,
    CONF_PERSON,
    CONF_PREHEAT_DURATION_S,
    CONF_PREHEAT_RADIUS_M,
    CONF_PROXIMITY_DIRECTION,
    CONF_PROXIMITY_DISTANCE,
    CONF_SOURCE_ZONES,
    CONF_WLAN_BENNI_TRACKER,
    CONF_WLAN_ELTERN_TRACKERS,
    DEFAULT_HOME_RADIUS_M,
    DEFAULT_HYSTERESIS_M,
    DEFAULT_NEAR_RADIUS_M,
    DEFAULT_PREHEAT_DURATION_S,
    DEFAULT_PREHEAT_RADIUS_M,
    MODULE_ID,
    NAME,
)


_TRACKER_DOMAINS = ["device_tracker", "person", "binary_sensor"]


def _entity_schema(defaults: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_ICLOUD_TRACKER,
            default=defaults.get(CONF_ICLOUD_TRACKER, vol.UNDEFINED),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=_TRACKER_DOMAINS, multiple=False)
        ),
        vol.Required(
            CONF_WLAN_BENNI_TRACKER,
            default=defaults.get(CONF_WLAN_BENNI_TRACKER, vol.UNDEFINED),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=_TRACKER_DOMAINS, multiple=False)
        ),
        vol.Required(
            CONF_PROXIMITY_DISTANCE,
            default=defaults.get(CONF_PROXIMITY_DISTANCE, vol.UNDEFINED),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "proximity"], multiple=False)
        ),
        vol.Required(
            CONF_PROXIMITY_DIRECTION,
            default=defaults.get(CONF_PROXIMITY_DIRECTION, vol.UNDEFINED),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "proximity"], multiple=False)
        ),
    }

    # Optionale Felder
    for opt_key in (CONF_MOBILE_TRACKER, CONF_PERSON):
        d = defaults.get(opt_key)
        marker = vol.Optional(opt_key, default=d) if d else vol.Optional(opt_key)
        fields[marker] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=_TRACKER_DOMAINS, multiple=False)
        )

    fields[
        vol.Optional(
            CONF_WLAN_ELTERN_TRACKERS,
            default=defaults.get(CONF_WLAN_ELTERN_TRACKERS, []),
        )
    ] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=_TRACKER_DOMAINS, multiple=True)
    )

    fields[
        vol.Optional(
            CONF_SOURCE_ZONES,
            default=defaults.get(CONF_SOURCE_ZONES, []),
        )
    ] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="zone", multiple=True)
    )

    return vol.Schema(fields)


def _threshold_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_HOME_RADIUS_M,
                default=defaults.get(CONF_HOME_RADIUS_M, DEFAULT_HOME_RADIUS_M),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=5000)),
            vol.Required(
                CONF_NEAR_RADIUS_M,
                default=defaults.get(CONF_NEAR_RADIUS_M, DEFAULT_NEAR_RADIUS_M),
            ): vol.All(vol.Coerce(int), vol.Range(min=50, max=10000)),
            vol.Required(
                CONF_PREHEAT_RADIUS_M,
                default=defaults.get(CONF_PREHEAT_RADIUS_M, DEFAULT_PREHEAT_RADIUS_M),
            ): vol.All(vol.Coerce(int), vol.Range(min=200, max=50000)),
            vol.Required(
                CONF_HYSTERESIS_M,
                default=defaults.get(CONF_HYSTERESIS_M, DEFAULT_HYSTERESIS_M),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=2000)),
            vol.Required(
                CONF_PREHEAT_DURATION_S,
                default=defaults.get(CONF_PREHEAT_DURATION_S, DEFAULT_PREHEAT_DURATION_S),
            ): vol.All(vol.Coerce(int), vol.Range(min=60, max=7200)),
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# ConfigFlow
# ─────────────────────────────────────────────────────────────────────────────


class ConfigFlowHelper:
    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow
        self._entities: dict[str, Any] = {}

    async def async_step_init(self) -> FlowResult:
        await self.flow.async_set_unique_id(f"{MODULE_ID}_singleton")
        self.flow._abort_if_unique_id_configured()
        return self.flow.async_show_form(
            step_id="module_step", data_schema=_entity_schema({})
        )

    async def async_step_module_step(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="module_step", data_schema=_entity_schema({})
            )
        self._entities = {k: v for k, v in user_input.items() if v not in ("", None, [])}
        return self.flow.async_show_form(
            step_id="thresholds", data_schema=_threshold_schema({})
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="thresholds", data_schema=_threshold_schema({})
            )
        data = {CONF_MODULE_ID: MODULE_ID, **self._entities}
        return self.flow.async_create_entry(title=NAME, data=data, options=user_input)


# ─────────────────────────────────────────────────────────────────────────────
# OptionsFlow
# ─────────────────────────────────────────────────────────────────────────────


class OptionsFlowHelper:
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.flow.async_show_menu(
            step_id="init", menu_options=["entities", "thresholds"]
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            new_data = {
                **self.entry.data,
                **{k: v for k, v in user_input.items() if v not in ("", None, [])},
            }
            # Felder die explizit geleert wurden raus
            for k in list(new_data):
                if k in user_input and user_input[k] in ("", None, []):
                    new_data.pop(k, None)
            new_data[CONF_MODULE_ID] = MODULE_ID
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.flow.async_create_entry(title="", data=self.entry.options)
        return self.flow.async_show_form(
            step_id="entities", data_schema=_entity_schema(self.entry.data)
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.flow.async_create_entry(title="", data=user_input)
        return self.flow.async_show_form(
            step_id="thresholds", data_schema=_threshold_schema(self.entry.options)
        )
