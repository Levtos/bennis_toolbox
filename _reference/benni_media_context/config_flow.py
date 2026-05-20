"""Config flow for benni_media_context."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_TV_ACTIVE, CONF_TV_SOURCE, CONF_TV_POWER_FALLBACK, CONF_APPLETV,
    CONF_PS5_STATUS, CONF_PS5_TITLE, CONF_SWITCH_DOCK, CONF_PC_ACTIVE,
    CONF_DENON_ACTIVE, CONF_HOMEPODS, CONF_TITLE_CLASSIFIER_PS5, CONF_TITLE_CLASSIFIER_PC,
    CONF_TITLE_CLASSIFIER_HOMEPODS, CONF_TITLE_CLASSIFIER_MEDIA, CONF_DOOR, CONF_CALL_MONITOR,
    CONF_DAY_STATE, CONF_ACTIVITY_STATE, CONF_WINDOW_STATE,
    CONF_DEBOUNCE, CONF_QUIET_DUCK, CONF_BASE_VOL_HOMEPODS, CONF_BASE_VOL_DENON,
    CONF_BOOST_OFFSET, CONF_WINDOW_OFFSET,
    DEFAULT_DEBOUNCE, DEFAULT_QUIET_DUCK, DEFAULT_BASE_VOL_HOMEPODS,
    DEFAULT_BASE_VOL_DENON, DEFAULT_BOOST_OFFSET, DEFAULT_WINDOW_OFFSET,
)

_ENTITY = selector.EntitySelector(selector.EntitySelectorConfig())
_ENTITY_MULTI = selector.EntitySelector(selector.EntitySelectorConfig(multiple=True))
_OPT_ENTITY = selector.EntitySelector(selector.EntitySelectorConfig())

_SOURCES_SCHEMA = vol.Schema({
    vol.Optional(CONF_TV_ACTIVE): _ENTITY,
    vol.Optional(CONF_TV_SOURCE): _ENTITY,
    vol.Optional(CONF_TV_POWER_FALLBACK): _ENTITY,
    vol.Optional(CONF_APPLETV): _ENTITY,
    vol.Optional(CONF_PS5_STATUS): _ENTITY,
    vol.Optional(CONF_PS5_TITLE): _ENTITY,
    vol.Optional(CONF_SWITCH_DOCK): _ENTITY,
    vol.Optional(CONF_PC_ACTIVE): _ENTITY,
    vol.Optional(CONF_DENON_ACTIVE): _ENTITY,
    vol.Optional(CONF_HOMEPODS): _ENTITY_MULTI,
    vol.Optional(CONF_TITLE_CLASSIFIER_PS5): _ENTITY,
    vol.Optional(CONF_TITLE_CLASSIFIER_PC): _ENTITY,
    vol.Optional(CONF_TITLE_CLASSIFIER_HOMEPODS): _ENTITY,
    vol.Optional(CONF_TITLE_CLASSIFIER_MEDIA): _ENTITY,
    vol.Optional(CONF_DOOR): _ENTITY,
    vol.Optional(CONF_CALL_MONITOR): _ENTITY,
    vol.Optional(CONF_DAY_STATE): _ENTITY,
    vol.Optional(CONF_ACTIVITY_STATE): _ENTITY,
    vol.Optional(CONF_WINDOW_STATE): _ENTITY,
})


def _number(min_: float, max_: float, step: float = 0.01):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=min_, max=max_, step=step, mode=selector.NumberSelectorMode.BOX)
    )


class BenniMediaContextConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Benni Media Context", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_SOURCES_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return BenniMediaContextOptionsFlow(entry)


class BenniMediaContextOptionsFlow(OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        o = self.entry.options
        schema = vol.Schema({
            vol.Optional(CONF_DEBOUNCE, default=o.get(CONF_DEBOUNCE, DEFAULT_DEBOUNCE)): _number(0, 60, 0.5),
            vol.Optional(CONF_QUIET_DUCK, default=o.get(CONF_QUIET_DUCK, DEFAULT_QUIET_DUCK)): _number(0, 1, 0.01),
            vol.Optional(CONF_BASE_VOL_HOMEPODS, default=o.get(CONF_BASE_VOL_HOMEPODS, DEFAULT_BASE_VOL_HOMEPODS)): _number(0, 1, 0.01),
            vol.Optional(CONF_BASE_VOL_DENON, default=o.get(CONF_BASE_VOL_DENON, DEFAULT_BASE_VOL_DENON)): _number(0, 1, 0.01),
            vol.Optional(CONF_BOOST_OFFSET, default=o.get(CONF_BOOST_OFFSET, DEFAULT_BOOST_OFFSET)): _number(-0.5, 0.5, 0.01),
            vol.Optional(CONF_WINDOW_OFFSET, default=o.get(CONF_WINDOW_OFFSET, DEFAULT_WINDOW_OFFSET)): _number(-0.5, 0.5, 0.01),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
