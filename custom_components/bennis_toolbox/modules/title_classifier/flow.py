"""Config- und Options-Flow-Helfer.

Mehrstufiger Add-Flow:
  module_step → (für `media`-Watcher) artist → Entry
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ...const import CONF_MODULE_ID
from .const import (
    CONF_ARTIST_ATTRIBUTE,
    CONF_AUTO_HIDE_HOURS,
    CONF_RETENTION_DAYS,
    CONF_SOURCE_ENTITY,
    CONF_WATCHER_TYPE,
    DEFAULT_ARTIST_ATTRIBUTE,
    MODULE_ID,
    WATCHER_TYPES,
)


# ---------------------------------------------------------------------------
# ConfigFlowHelper
# ---------------------------------------------------------------------------


class ConfigFlowHelper:
    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow
        self._user_input: dict[str, Any] = {}

    async def async_step_init(self) -> FlowResult:
        return self._show_user_form()

    async def async_step_module_step(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return self._show_user_form()
        # Eindeutiger unique_id pro Watcher-Name, damit doppelte Namen abgelehnt
        # werden — die HA-Flow-Manager prüft das vor dem Anlegen.
        await self.flow.async_set_unique_id(
            f"{MODULE_ID}_" + user_input[CONF_NAME].lower().replace(" ", "_")
        )
        self.flow._abort_if_unique_id_configured()
        self._user_input.update(user_input)
        if user_input[CONF_WATCHER_TYPE] == "media":
            return await self.async_step_artist()
        return self._create_entry()

    async def async_step_artist(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._user_input.update(user_input)
            return self._create_entry()

        state = self.hass.states.get(self._user_input[CONF_SOURCE_ENTITY])
        attrs = sorted(state.attributes) if state else []
        artist_candidates = [
            attr for attr in attrs if "artist" in attr.lower() or "author" in attr.lower()
        ]
        options = artist_candidates or attrs or [DEFAULT_ARTIST_ATTRIBUTE]
        default = (
            DEFAULT_ARTIST_ATTRIBUTE
            if DEFAULT_ARTIST_ATTRIBUTE in options
            else options[0]
        )
        return self.flow.async_show_form(
            step_id="artist",
            data_schema=vol.Schema({
                vol.Required(CONF_ARTIST_ATTRIBUTE, default=default): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode="dropdown", custom_value=True
                    )
                )
            }),
        )

    def _show_user_form(self) -> FlowResult:
        return self.flow.async_show_form(
            step_id="module_step",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME): selector.TextSelector(),
                vol.Required(CONF_SOURCE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["media_player", "sensor"])
                ),
                vol.Required(CONF_WATCHER_TYPE, default="media"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=list(WATCHER_TYPES))
                ),
                vol.Optional(CONF_RETENTION_DAYS): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, step=1, mode="box")
                ),
            }),
        )

    def _create_entry(self) -> FlowResult:
        data = {
            CONF_MODULE_ID: MODULE_ID,
            CONF_NAME: self._user_input[CONF_NAME],
            CONF_SOURCE_ENTITY: self._user_input[CONF_SOURCE_ENTITY],
            CONF_ARTIST_ATTRIBUTE: self._user_input.get(CONF_ARTIST_ATTRIBUTE),
            CONF_WATCHER_TYPE: self._user_input[CONF_WATCHER_TYPE],
        }
        options = {CONF_RETENTION_DAYS: self._user_input.get(CONF_RETENTION_DAYS)}
        return self.flow.async_create_entry(
            title=self._user_input[CONF_NAME], data=data, options=options
        )


# ---------------------------------------------------------------------------
# OptionsFlowHelper
# ---------------------------------------------------------------------------


class OptionsFlowHelper:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.flow.async_create_entry(title="", data=user_input)

        days_selector = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, step=1, mode="box")
        )
        hide_selector = selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, step=1, mode="box")
        )

        current_days = self.entry.options.get(CONF_RETENTION_DAYS)
        days_field = (
            vol.Optional(CONF_RETENTION_DAYS, default=int(current_days))
            if current_days is not None
            else vol.Optional(CONF_RETENTION_DAYS)
        )
        current_hide = self.entry.options.get(CONF_AUTO_HIDE_HOURS)
        hide_field = (
            vol.Optional(CONF_AUTO_HIDE_HOURS, default=int(current_hide))
            if current_hide is not None
            else vol.Optional(CONF_AUTO_HIDE_HOURS)
        )
        return self.flow.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                days_field: days_selector,
                hide_field: hide_selector,
            }),
        )
