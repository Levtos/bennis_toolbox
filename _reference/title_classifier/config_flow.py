"""Config flow for Entity Title Mapper."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

from .const import (
    CONF_ARTIST_ATTRIBUTE,
    CONF_AUTO_HIDE_HOURS,
    CONF_RETENTION_DAYS,
    CONF_SOURCE_ENTITY,
    CONF_WATCHER_TYPE,
    DEFAULT_ARTIST_ATTRIBUTE,
    DOMAIN,
    WATCHER_TYPES,
)


class TitleClassifierConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Title Classifier watcher config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
        self._user_input: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create a watcher."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_NAME].lower().replace(" ", "_"))
            self._abort_if_unique_id_configured()
            self._user_input.update(user_input)
            if user_input[CONF_WATCHER_TYPE] == "media":
                return await self.async_step_artist()
            return self._create_entry()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.TextSelector(),
                    vol.Required(CONF_SOURCE_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["media_player", "sensor"])
                    ),
                    vol.Required(CONF_WATCHER_TYPE, default="media"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=WATCHER_TYPES)
                    ),
                    vol.Optional(CONF_RETENTION_DAYS): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, step=1, mode="box")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_artist(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Select the artist attribute for media watchers."""
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

        return self.async_show_form(
            step_id="artist",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ARTIST_ATTRIBUTE, default=default): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options, mode="dropdown", custom_value=True
                        )
                    )
                }
            ),
        )

    def _create_entry(self) -> config_entries.ConfigFlowResult:
        """Create the watcher config entry from collected flow data."""
        data = {
            CONF_NAME: self._user_input[CONF_NAME],
            CONF_SOURCE_ENTITY: self._user_input[CONF_SOURCE_ENTITY],
            CONF_ARTIST_ATTRIBUTE: self._user_input.get(CONF_ARTIST_ATTRIBUTE),
            CONF_WATCHER_TYPE: self._user_input[CONF_WATCHER_TYPE],
        }
        options = {CONF_RETENTION_DAYS: self._user_input.get(CONF_RETENTION_DAYS)}
        return self.async_create_entry(
            title=self._user_input[CONF_NAME], data=data, options=options
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> TitleClassifierOptionsFlow:
        """Return the options flow."""
        return TitleClassifierOptionsFlow(config_entry)


class TitleClassifierOptionsFlow(config_entries.OptionsFlow):
    """Handle watcher options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialise options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Edit retention and auto-hide options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        days_selector = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, step=1, mode="box")
        )
        hide_selector = selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, step=1, mode="box")
        )

        current_days = self._config_entry.options.get(CONF_RETENTION_DAYS)
        days_field = (
            vol.Optional(CONF_RETENTION_DAYS, default=int(current_days))
            if current_days is not None
            else vol.Optional(CONF_RETENTION_DAYS)
        )

        current_hide = self._config_entry.options.get(CONF_AUTO_HIDE_HOURS)
        hide_field = (
            vol.Optional(CONF_AUTO_HIDE_HOURS, default=int(current_hide))
            if current_hide is not None
            else vol.Optional(CONF_AUTO_HIDE_HOURS)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    days_field: days_selector,
                    hide_field: hide_selector,
                }
            ),
        )
