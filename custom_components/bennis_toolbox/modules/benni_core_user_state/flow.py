"""Config- und Options-Flow-Helfer für Benni Core · User State.

Pflichtfeld:
- `day_state_source` — Sensor, dessen `master_phase`-Attribut die Wake-Trigger
  gaten (LH R-US-06, R-US-07). Default `sensor.benni_core_day_state`.

Optionale Felder:
- `pc_active_entity`     — binary_sensor / switch (Sleep-Guard + Wake)
- `ps5_active_entity`    — binary_sensor / switch (Wake)
- `coffee_active_entity` — binary_sensor / switch (Wake)
- `opening_entities`     — Liste Fenster/Türen, deren state-change als Wake zählt

Single-Instance: nur eine User-State-Instanz erlaubt.
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
    CONF_DAY_STATE_SOURCE,
    CONF_OPENING_ENTITIES,
    CONF_PC_ACTIVE,
    CONF_PS5_ACTIVE,
    DEFAULT_DAY_STATE_SOURCE,
    MODULE_ID,
    NAME,
)

_BINARY_DOMAINS: list[str] = ["binary_sensor", "switch", "input_boolean"]
_OPENING_DOMAINS: list[str] = ["binary_sensor", "input_boolean"]


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_DAY_STATE_SOURCE,
            default=defaults.get(CONF_DAY_STATE_SOURCE, DEFAULT_DAY_STATE_SOURCE),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor"], multiple=False)
        ),
    }

    for key in (CONF_PC_ACTIVE, CONF_PS5_ACTIVE, CONF_COFFEE_ACTIVE):
        d = defaults.get(key)
        marker = vol.Optional(key, default=d) if d else vol.Optional(key)
        fields[marker] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=_BINARY_DOMAINS, multiple=False)
        )

    fields[vol.Optional(
        CONF_OPENING_ENTITIES, default=defaults.get(CONF_OPENING_ENTITIES, [])
    )] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=_OPENING_DOMAINS, multiple=True)
    )

    return vol.Schema(fields)


# ─────────────────────────────────────────────────────────────────────────────
# ConfigFlowHelper
# ─────────────────────────────────────────────────────────────────────────────


class ConfigFlowHelper:
    """Wird vom zentralen BennisToolboxConfigFlow aufgerufen."""

    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow

    async def async_step_init(self) -> FlowResult:
        await self.flow.async_set_unique_id(f"{MODULE_ID}_singleton")
        self.flow._abort_if_unique_id_configured()
        return self.flow.async_show_form(
            step_id="module_step", data_schema=_schema({})
        )

    async def async_step_module_step(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="module_step", data_schema=_schema({})
            )
        # Leere Strings aus optionalen Feldern droppen — sonst speichert HA
        # "" als gültigen Wert und der Coordinator versucht "" zu lesen.
        cleaned = {k: v for k, v in user_input.items() if v not in ("", None, [])}
        data = {CONF_MODULE_ID: MODULE_ID, **cleaned}
        return self.flow.async_create_entry(title=NAME, data=data)


# ─────────────────────────────────────────────────────────────────────────────
# OptionsFlowHelper
# ─────────────────────────────────────────────────────────────────────────────


class OptionsFlowHelper:
    """Erlaubt nachträgliches Anpassen aller Slots."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            cleaned = {k: v for k, v in user_input.items() if v not in ("", None, [])}
            new_data = {**self.entry.data, **cleaned}
            # Felder die der User explizit geleert hat → aus data raus
            for key in (CONF_PC_ACTIVE, CONF_PS5_ACTIVE, CONF_COFFEE_ACTIVE):
                if key in user_input and not user_input[key]:
                    new_data.pop(key, None)
            new_data[CONF_MODULE_ID] = MODULE_ID
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.flow.async_create_entry(title="", data={})
        return self.flow.async_show_form(
            step_id="init", data_schema=_schema(self.entry.data)
        )
