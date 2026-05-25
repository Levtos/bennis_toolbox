"""Config- und Options-Flow-Helfer für Benni Core · Day State.

Ein Pflichtfeld: `solar_noon_source` (Entity, die heutigen Solar Noon
liefert). Default `sun.sun` — wir extrahieren `next_noon` mit 24h-Korrektur
im Coordinator.

Single-Instance: nur eine Day-State-Instanz erlaubt (unique_id
`benni_core_day_state_singleton`).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ...const import CONF_MODULE_ID
from .const import CONF_SOLAR_NOON_SOURCE, DEFAULT_SOLAR_NOON_SOURCE

MODULE_ID = "benni_core_day_state"
NAME = "Benni Core · Day State"


def _source_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Schema für den einen Pflicht-Slot."""
    return vol.Schema(
        {
            vol.Required(
                CONF_SOLAR_NOON_SOURCE,
                default=defaults.get(CONF_SOLAR_NOON_SOURCE, DEFAULT_SOLAR_NOON_SOURCE),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["sensor", "sun"],
                    multiple=False,
                )
            ),
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# ConfigFlowHelper
# ─────────────────────────────────────────────────────────────────────────────


class ConfigFlowHelper:
    """Wird vom zentralen BennisToolboxConfigFlow aufgerufen."""

    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow

    async def async_step_init(self) -> FlowResult:
        # Single-Instance-Gate.
        await self.flow.async_set_unique_id(f"{MODULE_ID}_singleton")
        self.flow._abort_if_unique_id_configured()
        return self.flow.async_show_form(
            step_id="module_step",
            data_schema=_source_schema({}),
        )

    async def async_step_module_step(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="module_step",
                data_schema=_source_schema({}),
            )
        data = {CONF_MODULE_ID: MODULE_ID, **user_input}
        return self.flow.async_create_entry(title=NAME, data=data)


# ─────────────────────────────────────────────────────────────────────────────
# OptionsFlowHelper
# ─────────────────────────────────────────────────────────────────────────────


class OptionsFlowHelper:
    """Erlaubt nachträgliches Wechseln der Solar-Noon-Quelle."""

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
            new_data = {**self.entry.data, **user_input}
            new_data[CONF_MODULE_ID] = MODULE_ID
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.flow.async_create_entry(title="", data={})
        return self.flow.async_show_form(
            step_id="init",
            data_schema=_source_schema(self.entry.data),
        )
