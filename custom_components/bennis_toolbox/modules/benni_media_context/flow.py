"""Config- und Options-Flow-Helfer für Benni Media Context.

Single-Instance über unique_id `benni_media_context_singleton`.

Add-Flow (1 Schritt):
  module_step — alle Quell-Entities sind optional.

Options-Flow (1 Schritt):
  init — Volumen/Debounce-Parameter.
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
    CONF_ACTIVITY_STATE,
    CONF_APPLETV,
    CONF_BASE_VOL_DENON,
    CONF_BASE_VOL_HOMEPODS,
    CONF_BOOST_OFFSET,
    CONF_CALL_MONITOR,
    CONF_DAY_STATE,
    CONF_DEBOUNCE,
    CONF_DENON_ACTIVE,
    CONF_DOOR,
    CONF_HOMEPODS,
    CONF_PC_ACTIVE,
    CONF_PS5_STATUS,
    CONF_PS5_TITLE,
    CONF_QUIET_DUCK,
    CONF_SWITCH_DOCK,
    CONF_TITLE_CLASSIFIER_HOMEPODS,
    CONF_TITLE_CLASSIFIER_MEDIA,
    CONF_TITLE_CLASSIFIER_PC,
    CONF_TITLE_CLASSIFIER_PS5,
    CONF_TV_ACTIVE,
    CONF_TV_POWER_FALLBACK,
    CONF_TV_SOURCE,
    CONF_WINDOW_OFFSET,
    CONF_WINDOW_STATE,
    DEFAULT_BASE_VOL_DENON,
    DEFAULT_BASE_VOL_HOMEPODS,
    DEFAULT_BOOST_OFFSET,
    DEFAULT_DEBOUNCE,
    DEFAULT_QUIET_DUCK,
    DEFAULT_WINDOW_OFFSET,
    MODULE_ID,
    NAME,
)

_ENTITY = selector.EntitySelector(selector.EntitySelectorConfig())
_ENTITY_MULTI = selector.EntitySelector(selector.EntitySelectorConfig(multiple=True))


def _sources_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}

    def _opt(key: str, sel):
        marker = vol.Optional(key, default=d[key]) if d.get(key) else vol.Optional(key)
        return marker, sel

    fields: dict[Any, Any] = {}
    for k in (
        CONF_TV_ACTIVE, CONF_TV_SOURCE, CONF_TV_POWER_FALLBACK, CONF_APPLETV,
        CONF_PS5_STATUS, CONF_PS5_TITLE, CONF_SWITCH_DOCK, CONF_PC_ACTIVE,
        CONF_DENON_ACTIVE,
    ):
        m, s = _opt(k, _ENTITY)
        fields[m] = s
    m, s = _opt(CONF_HOMEPODS, _ENTITY_MULTI)
    fields[m] = s
    for k in (
        CONF_TITLE_CLASSIFIER_PS5, CONF_TITLE_CLASSIFIER_PC,
        CONF_TITLE_CLASSIFIER_HOMEPODS, CONF_TITLE_CLASSIFIER_MEDIA,
        CONF_DOOR, CONF_CALL_MONITOR, CONF_DAY_STATE, CONF_ACTIVITY_STATE,
        CONF_WINDOW_STATE,
    ):
        m, s = _opt(k, _ENTITY)
        fields[m] = s
    return vol.Schema(fields)


def _number(min_: float, max_: float, step: float = 0.01) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_, max=max_, step=step, mode=selector.NumberSelectorMode.BOX
        )
    )


def _options_schema(opts: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Optional(CONF_DEBOUNCE, default=opts.get(CONF_DEBOUNCE, DEFAULT_DEBOUNCE)):
            _number(0, 60, 0.5),
        vol.Optional(CONF_QUIET_DUCK, default=opts.get(CONF_QUIET_DUCK, DEFAULT_QUIET_DUCK)):
            _number(0, 1, 0.01),
        vol.Optional(CONF_BASE_VOL_HOMEPODS, default=opts.get(CONF_BASE_VOL_HOMEPODS, DEFAULT_BASE_VOL_HOMEPODS)):
            _number(0, 1, 0.01),
        vol.Optional(CONF_BASE_VOL_DENON, default=opts.get(CONF_BASE_VOL_DENON, DEFAULT_BASE_VOL_DENON)):
            _number(0, 1, 0.01),
        vol.Optional(CONF_BOOST_OFFSET, default=opts.get(CONF_BOOST_OFFSET, DEFAULT_BOOST_OFFSET)):
            _number(-0.5, 0.5, 0.01),
        vol.Optional(CONF_WINDOW_OFFSET, default=opts.get(CONF_WINDOW_OFFSET, DEFAULT_WINDOW_OFFSET)):
            _number(-0.5, 0.5, 0.01),
    })


# ---------------------------------------------------------------------------
# ConfigFlowHelper
# ---------------------------------------------------------------------------


class ConfigFlowHelper:
    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow

    async def async_step_init(self) -> FlowResult:
        await self.flow.async_set_unique_id(f"{MODULE_ID}_singleton")
        self.flow._abort_if_unique_id_configured()
        return self.flow.async_show_form(
            step_id="module_step", data_schema=_sources_schema(),
        )

    async def async_step_module_step(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="module_step", data_schema=_sources_schema(),
            )
        data: dict[str, Any] = {CONF_MODULE_ID: MODULE_ID}
        data.update({k: v for k, v in user_input.items() if v not in (None, "", [])})
        return self.flow.async_create_entry(title=NAME, data=data)


# ---------------------------------------------------------------------------
# OptionsFlowHelper
# ---------------------------------------------------------------------------


def _merged(entry: ConfigEntry) -> dict[str, Any]:
    """Defaults seen by edit forms: options win over original data."""
    merged = dict(entry.data)
    merged.update(entry.options)
    merged.pop(CONF_MODULE_ID, None)
    return merged


class OptionsFlowHelper:
    """Two-step options menu.

    The 0.3.5.4 build only exposed the volume/debounce tuning. Users
    couldn't change media sources after the initial add — every fix
    required deleting and re-adding the entry. The new menu surfaces
    both surfaces explicitly: ``sources`` for media-related entities,
    ``tuning`` for the volume/debounce knobs.

    Source values are stored in ``entry.options`` from here on (the
    coordinator now reads merged options-over-data, so legacy entries
    keep working without migration).
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.flow.async_show_menu(
            step_id="init", menu_options=["sources", "tuning"],
        )

    async def async_step_sources(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            # Drop empty slots so the coordinator's merge keeps falling
            # back to entry.data for keys the user cleared.
            cleaned = {k: v for k, v in user_input.items() if v not in (None, "", [])}
            new_opts = {**self.entry.options}
            # Wipe any source key the user *omitted* from the form (HA
            # only submits the keys present in the schema) so legacy
            # data-side values surface again instead of being overridden
            # by stale options.
            for k in cleaned:
                new_opts[k] = cleaned[k]
            new_opts.pop(CONF_MODULE_ID, None)
            return self.flow.async_create_entry(title="", data=new_opts)
        return self.flow.async_show_form(
            step_id="sources", data_schema=_sources_schema(_merged(self.entry)),
        )

    async def async_step_tuning(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            new_opts = {**self.entry.options, **user_input}
            new_opts.pop(CONF_MODULE_ID, None)
            return self.flow.async_create_entry(title="", data=new_opts)
        return self.flow.async_show_form(
            step_id="tuning", data_schema=_options_schema(_merged(self.entry)),
        )
