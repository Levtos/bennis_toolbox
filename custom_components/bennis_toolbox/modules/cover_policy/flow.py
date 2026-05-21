"""Config- und Options-Flow für Cover Policy.

Mehrere Cover-Instanzen sind erlaubt; unique_id ist die Cover-Entity-ID,
damit das gleiche Cover nicht doppelt verpolicyt wird.

Add-Flow (1 Schritt): Name + Cover-Entity + alle optionalen Quellen +
Apply-Toggle + Override-Dauer + Startup-Block.

Options-Flow (Menü): sources | profile | runtime.
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
    CONF_APPLY_ENABLED,
    CONF_BIO_STATE,
    CONF_COVER_ENTITY,
    CONF_DAY_CONTEXT,
    CONF_DAY_STATE,
    CONF_GAMING_SOURCE,
    CONF_HEAT_PROTECT_ACTIVE,
    CONF_LUX,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MEDIA_CONTEXT,
    CONF_NAME,
    CONF_PRESENCE_HOUSEHOLD,
    CONF_PRESENCE_PERSONAL,
    CONF_PROFILE,
    CONF_STARTUP_BLOCK_SECONDS,
    CONF_SUN,
    CONF_WEATHER,
    CONF_WINDOW_STATE,
    DEFAULT_APPLY_ENABLED,
    DEFAULT_MANUAL_OVERRIDE_DURATION,
    DEFAULT_PROFILE,
    DEFAULT_STARTUP_BLOCK_SECONDS,
    MODULE_ID,
    PROFILE_MODES,
)


def _esel(domains: list[str] | None = None) -> selector.EntitySelector:
    cfg: dict[str, Any] = {"multiple": False}
    if domains:
        cfg["domain"] = domains
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


def _sources_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}

    def _opt(key: str, sel):
        marker = vol.Optional(key, default=d[key]) if d.get(key) else vol.Optional(key)
        return marker, sel

    fields: dict[Any, Any] = {}
    for k, doms in (
        (CONF_WINDOW_STATE, ["binary_sensor", "input_boolean", "sensor"]),
        (CONF_BIO_STATE, ["sensor", "input_select"]),
        (CONF_PRESENCE_HOUSEHOLD, ["sensor", "input_select"]),
        (CONF_PRESENCE_PERSONAL, ["sensor", "input_select"]),
        (CONF_DAY_STATE, ["sensor", "input_select"]),
        (CONF_DAY_CONTEXT, ["sensor", "input_select"]),
        (CONF_LUX, ["sensor"]),
        (CONF_SUN, ["sun", "sensor"]),
        (CONF_WEATHER, ["weather", "sensor"]),
        (CONF_MEDIA_CONTEXT, ["sensor", "input_select"]),
        (CONF_GAMING_SOURCE, ["sensor", "input_select"]),
        (CONF_HEAT_PROTECT_ACTIVE, ["binary_sensor", "input_boolean"]),
    ):
        m, s = _opt(k, _esel(doms))
        fields[m] = s
    return vol.Schema(fields)


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    base = vol.Schema({
        vol.Required(CONF_NAME, default=d.get(CONF_NAME, "")): str,
        vol.Required(CONF_COVER_ENTITY, default=d.get(CONF_COVER_ENTITY) or vol.UNDEFINED):
            _esel(["cover"]),
    })
    # Extend with sources and runtime options.
    sources = _sources_schema(d).schema
    runtime = vol.Schema({
        vol.Optional(CONF_APPLY_ENABLED, default=d.get(CONF_APPLY_ENABLED, DEFAULT_APPLY_ENABLED)): bool,
        vol.Optional(CONF_MANUAL_OVERRIDE_DURATION, default=d.get(CONF_MANUAL_OVERRIDE_DURATION, DEFAULT_MANUAL_OVERRIDE_DURATION)):
            vol.All(int, vol.Range(min=0, max=86400)),
        vol.Optional(CONF_STARTUP_BLOCK_SECONDS, default=d.get(CONF_STARTUP_BLOCK_SECONDS, DEFAULT_STARTUP_BLOCK_SECONDS)):
            vol.All(int, vol.Range(min=0, max=3600)),
    }).schema
    return vol.Schema({**base.schema, **sources, **runtime})


def _position_selector() -> selector.NumberSelector:
    """0..100 % slider for one target position.

    Convention: 0 = closed/down, 100 = open/up (HA standard).
    """
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=100, step=1,
            mode=selector.NumberSelectorMode.SLIDER,
            unit_of_measurement="%",
        )
    )


def _profile_schema(profile: dict[str, int]) -> vol.Schema:
    """Position profile editor.

    One slider per mode; translations under `options.step.profile.data.*`
    explain what each mode means (Schlafen / Aufwachen / Hitzeschutz / …).
    Slider values are coerced back to int to keep the wire format stable
    with `policy.decide()`.
    """
    fields: dict[Any, Any] = {}
    for m in PROFILE_MODES:
        default = int(profile.get(m, DEFAULT_PROFILE[m]))
        fields[vol.Required(m, default=default)] = vol.All(
            _position_selector(), vol.Coerce(int), vol.Range(min=0, max=100),
        )
    return vol.Schema(fields)


def _runtime_options_schema(opts: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Optional(CONF_APPLY_ENABLED, default=opts.get(CONF_APPLY_ENABLED, DEFAULT_APPLY_ENABLED)): bool,
        vol.Optional(CONF_MANUAL_OVERRIDE_DURATION, default=opts.get(CONF_MANUAL_OVERRIDE_DURATION, DEFAULT_MANUAL_OVERRIDE_DURATION)):
            vol.All(int, vol.Range(min=0, max=86400)),
        vol.Optional(CONF_STARTUP_BLOCK_SECONDS, default=opts.get(CONF_STARTUP_BLOCK_SECONDS, DEFAULT_STARTUP_BLOCK_SECONDS)):
            vol.All(int, vol.Range(min=0, max=3600)),
    })


# ---------------------------------------------------------------------------
# ConfigFlowHelper
# ---------------------------------------------------------------------------


class ConfigFlowHelper:
    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow

    async def async_step_init(self) -> FlowResult:
        return self.flow.async_show_form(
            step_id="module_step", data_schema=_user_schema(),
        )

    async def async_step_module_step(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="module_step", data_schema=_user_schema(),
            )

        cover_entity = user_input.get(CONF_COVER_ENTITY)
        if not cover_entity:
            return self.flow.async_show_form(
                step_id="module_step",
                data_schema=_user_schema(user_input),
                errors={CONF_COVER_ENTITY: "required"},
            )

        # One config entry per unique cover.
        await self.flow.async_set_unique_id(f"{MODULE_ID}:{cover_entity}")
        self.flow._abort_if_unique_id_configured()

        title = user_input.get(CONF_NAME) or f"Cover Policy ({cover_entity})"
        data: dict[str, Any] = {CONF_MODULE_ID: MODULE_ID, CONF_NAME: user_input[CONF_NAME], CONF_COVER_ENTITY: cover_entity}
        # Source entity slots → data; runtime knobs → options.
        for k in (
            CONF_WINDOW_STATE, CONF_BIO_STATE, CONF_PRESENCE_HOUSEHOLD,
            CONF_PRESENCE_PERSONAL, CONF_DAY_STATE, CONF_DAY_CONTEXT,
            CONF_LUX, CONF_SUN, CONF_WEATHER,
            CONF_MEDIA_CONTEXT, CONF_GAMING_SOURCE, CONF_HEAT_PROTECT_ACTIVE,
        ):
            if user_input.get(k):
                data[k] = user_input[k]
        options: dict[str, Any] = {
            CONF_APPLY_ENABLED: bool(user_input.get(CONF_APPLY_ENABLED, DEFAULT_APPLY_ENABLED)),
            CONF_MANUAL_OVERRIDE_DURATION: int(user_input.get(CONF_MANUAL_OVERRIDE_DURATION, DEFAULT_MANUAL_OVERRIDE_DURATION)),
            CONF_STARTUP_BLOCK_SECONDS: int(user_input.get(CONF_STARTUP_BLOCK_SECONDS, DEFAULT_STARTUP_BLOCK_SECONDS)),
            CONF_PROFILE: dict(DEFAULT_PROFILE),
        }
        return self.flow.async_create_entry(title=title, data=data, options=options)


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
            step_id="init", menu_options=["sources", "profile", "runtime"],
        )

    async def async_step_sources(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            new_data = dict(self.entry.data)
            for k in (
                CONF_WINDOW_STATE, CONF_BIO_STATE, CONF_PRESENCE_HOUSEHOLD,
                CONF_PRESENCE_PERSONAL, CONF_DAY_STATE, CONF_DAY_CONTEXT,
                CONF_LUX, CONF_SUN, CONF_WEATHER,
                CONF_MEDIA_CONTEXT, CONF_GAMING_SOURCE, CONF_HEAT_PROTECT_ACTIVE,
            ):
                if user_input.get(k):
                    new_data[k] = user_input[k]
                else:
                    new_data.pop(k, None)
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.flow.async_create_entry(title="", data=self.entry.options)
        return self.flow.async_show_form(
            step_id="sources", data_schema=_sources_schema(self.entry.data),
        )

    async def async_step_profile(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        current = {**DEFAULT_PROFILE, **(self.entry.options.get(CONF_PROFILE) or {})}
        if user_input is not None:
            new_options = {**self.entry.options, CONF_PROFILE: {**current, **user_input}}
            return self.flow.async_create_entry(title="", data=new_options)
        return self.flow.async_show_form(
            step_id="profile", data_schema=_profile_schema(current),
        )

    async def async_step_runtime(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            new_options = {**self.entry.options, **user_input}
            return self.flow.async_create_entry(title="", data=new_options)
        return self.flow.async_show_form(
            step_id="runtime", data_schema=_runtime_options_schema(self.entry.options),
        )
