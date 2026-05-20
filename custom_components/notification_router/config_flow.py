"""Config and options flow for notification_router."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ACTIVITY_STATE, CONF_BIO_STATE, CONF_DOORBELL_STATE,
    CONF_HEADSET_ACTIVE, CONF_LIGHT_SCRIPT, CONF_LOCK_BATTERY,
    CONF_MEDIA_CONTEXT, CONF_MEDIA_SCRIPT, CONF_NOTIFY_TARGETS,
    CONF_OPENING_SAFETY, CONF_PRESENCE_PERSONAL, CONF_QUIET_MODE_ACTIVE,
    DEFAULT_RATE_LIMIT, DOMAIN, EVENT_CLASSES,
    OPT_COOLDOWNS, OPT_HEADSET_BEHAVIOR, OPT_PRIVATE_TIME_BEHAVIOR,
    OPT_QUIET_HOURS_END, OPT_QUIET_HOURS_START, OPT_RATE_LIMIT,
    OPT_SEVERITY_MAP, OPT_SLEEP_BEHAVIOR, SEVERITIES,
)


def _entity_selector(domains: list[str] | None = None) -> selector.EntitySelector:
    cfg = selector.EntitySelectorConfig(multiple=False)
    if domains:
        cfg["domain"] = domains
    return selector.EntitySelector(cfg)


def _multi_entity_selector(domains: list[str] | None = None) -> selector.EntitySelector:
    cfg = selector.EntitySelectorConfig(multiple=True)
    if domains:
        cfg["domain"] = domains
    return selector.EntitySelector(cfg)


def _build_user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Optional(CONF_BIO_STATE, default=d.get(CONF_BIO_STATE, vol.UNDEFINED)): _entity_selector(),
        vol.Optional(CONF_ACTIVITY_STATE, default=d.get(CONF_ACTIVITY_STATE, vol.UNDEFINED)): _entity_selector(),
        vol.Optional(CONF_PRESENCE_PERSONAL, default=d.get(CONF_PRESENCE_PERSONAL, vol.UNDEFINED)): _entity_selector(),
        vol.Optional(CONF_MEDIA_CONTEXT, default=d.get(CONF_MEDIA_CONTEXT, vol.UNDEFINED)): _entity_selector(),
        vol.Optional(CONF_HEADSET_ACTIVE, default=d.get(CONF_HEADSET_ACTIVE, vol.UNDEFINED)): _entity_selector(["binary_sensor", "input_boolean", "switch"]),
        vol.Optional(CONF_QUIET_MODE_ACTIVE, default=d.get(CONF_QUIET_MODE_ACTIVE, vol.UNDEFINED)): _entity_selector(["binary_sensor", "input_boolean", "switch"]),
        vol.Optional(CONF_DOORBELL_STATE, default=d.get(CONF_DOORBELL_STATE, vol.UNDEFINED)): _entity_selector(),
        vol.Optional(CONF_OPENING_SAFETY, default=d.get(CONF_OPENING_SAFETY, vol.UNDEFINED)): _entity_selector(),
        vol.Optional(CONF_LOCK_BATTERY, default=d.get(CONF_LOCK_BATTERY, vol.UNDEFINED)): _entity_selector(["sensor", "binary_sensor"]),
        vol.Optional(CONF_NOTIFY_TARGETS, default=d.get(CONF_NOTIFY_TARGETS, [])): selector.TextSelector(
            selector.TextSelectorConfig(multiple=True)
        ),
        vol.Optional(CONF_LIGHT_SCRIPT, default=d.get(CONF_LIGHT_SCRIPT, vol.UNDEFINED)): _entity_selector(["script", "scene"]),
        vol.Optional(CONF_MEDIA_SCRIPT, default=d.get(CONF_MEDIA_SCRIPT, vol.UNDEFINED)): _entity_selector(["script"]),
    })


class BenniNotificationRouterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            # Strip empty values
            clean = {k: v for k, v in user_input.items() if v not in (None, "", [])}
            return self.async_create_entry(title="Benni Notification Router", data=clean)
        return self.async_show_form(step_id="user", data_schema=_build_user_schema())

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return BenniNotificationRouterOptionsFlow(entry)


class BenniNotificationRouterOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        opts = self.entry.options
        schema = vol.Schema({
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
        return self.async_show_form(step_id="init", data_schema=schema)
