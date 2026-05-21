"""Config- und Options-Flow-Helfer für Notification Router.

Single-Instance via unique_id `notification_router_singleton`.

Add-Flow (1 Schritt `module_step`): Context-Quellen + optionale Output-Targets.

Options-Flow (1 Schritt `init`): Quiet Hours / Sleep / Private / Headset
Behavior / Rate Limit / Severity-Map / Cooldowns.
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
    CONF_BIO_STATE,
    CONF_DOORBELL_STATE,
    CONF_HEADSET_ACTIVE,
    CONF_LIGHT_SCRIPT,
    CONF_LOCK_BATTERY,
    CONF_MEDIA_CONTEXT,
    CONF_MEDIA_SCRIPT,
    CONF_NOTIFY_TARGETS,
    CONF_OPENING_SAFETY,
    CONF_PRESENCE_PERSONAL,
    CONF_QUIET_MODE_ACTIVE,
    DEFAULT_RATE_LIMIT,
    MODULE_ID,
    NAME,
    OPT_COOLDOWNS,
    OPT_HEADSET_BEHAVIOR,
    OPT_PRIVATE_TIME_BEHAVIOR,
    OPT_QUIET_HOURS_END,
    OPT_QUIET_HOURS_START,
    OPT_RATE_LIMIT,
    OPT_SEVERITY_MAP,
    OPT_SLEEP_BEHAVIOR,
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
    for k in (CONF_BIO_STATE, CONF_ACTIVITY_STATE, CONF_PRESENCE_PERSONAL, CONF_MEDIA_CONTEXT):
        m, s = _opt(k, _esel())
        fields[m] = s
    for k in (CONF_HEADSET_ACTIVE, CONF_QUIET_MODE_ACTIVE):
        m, s = _opt(k, _esel(["binary_sensor", "input_boolean", "switch"]))
        fields[m] = s
    for k in (CONF_DOORBELL_STATE, CONF_OPENING_SAFETY):
        m, s = _opt(k, _esel())
        fields[m] = s
    m, s = _opt(CONF_LOCK_BATTERY, _esel(["sensor", "binary_sensor"]))
    fields[m] = s
    # Optional output targets.
    notify_default = d.get(CONF_NOTIFY_TARGETS, [])
    fields[vol.Optional(CONF_NOTIFY_TARGETS, default=notify_default)] = (
        selector.TextSelector(selector.TextSelectorConfig(multiple=True))
    )
    m, s = _opt(CONF_LIGHT_SCRIPT, _esel(["script", "scene"]))
    fields[m] = s
    m, s = _opt(CONF_MEDIA_SCRIPT, _esel(["script"]))
    fields[m] = s
    return vol.Schema(fields)


def _options_schema(opts: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Optional(OPT_QUIET_HOURS_START, default=opts.get(OPT_QUIET_HOURS_START, "22:00")): str,
        vol.Optional(OPT_QUIET_HOURS_END, default=opts.get(OPT_QUIET_HOURS_END, "07:00")): str,
        vol.Optional(OPT_SLEEP_BEHAVIOR, default=opts.get(OPT_SLEEP_BEHAVIOR, "critical_only")):
            vol.In(["silent", "soft", "critical_only"]),
        vol.Optional(OPT_PRIVATE_TIME_BEHAVIOR, default=opts.get(OPT_PRIVATE_TIME_BEHAVIOR, "mask")):
            vol.In(["mask", "suppress", "normal"]),
        vol.Optional(OPT_HEADSET_BEHAVIOR, default=opts.get(OPT_HEADSET_BEHAVIOR, "light_push")):
            vol.In(["light_push", "push_only", "normal"]),
        vol.Optional(OPT_RATE_LIMIT, default=opts.get(OPT_RATE_LIMIT, DEFAULT_RATE_LIMIT)):
            vol.All(int, vol.Range(min=1, max=600)),
        vol.Optional(OPT_SEVERITY_MAP, default=opts.get(OPT_SEVERITY_MAP, {})):
            selector.ObjectSelector(),
        vol.Optional(OPT_COOLDOWNS, default=opts.get(OPT_COOLDOWNS, {})):
            selector.ObjectSelector(),
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


class OptionsFlowHelper:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.flow.async_create_entry(title="", data=user_input)
        return self.flow.async_show_form(
            step_id="init", data_schema=_options_schema(self.entry.options),
        )
