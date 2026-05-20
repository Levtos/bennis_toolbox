"""Config & options flow.

Hub entry holds the global selectors plus a list of devices. Devices are
added/edited/removed via the options flow (one at a time, so the UI stays sane).
"""
from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN, ALL_POLICIES, ALL_KINDS,
    CONF_DEVICES, CONF_NAME, CONF_SWITCH, CONF_POWER, CONF_BATTERY,
    CONF_POLICY, CONF_KIND, CONF_ACTIVE_THRESHOLD, CONF_IDLE_THRESHOLD,
    CONF_DEADBAND_LOW, CONF_DEADBAND_HIGH, CONF_STABLE_OFF, CONF_UNKNOWN,
    CONF_ALLOWED_CONTEXTS, CONF_NEVER_CUT_ACTIVE, CONF_WAKE_SIGNAL_ONLY,
    CONF_TABLET_LOW, CONF_TABLET_HIGH, CONF_DIFFUSER_ON_MIN, CONF_DIFFUSER_OFF_MIN,
    CONF_MANUAL_COOLDOWN,
    CONF_PRESENCE, CONF_BIO, CONF_DAY, CONF_MEDIA, CONF_ENTERTAINMENT, CONF_ACTIVITY,
    CONF_ENABLE_CONTROL, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL,
    UNK_ASSUME_ACTIVE, UNK_ASSUME_IDLE,
)


def _entity(domain: str | list[str] | None = None):
    cfg: dict = {}
    if domain:
        cfg["domain"] = domain
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


_GLOBAL_SCHEMA = vol.Schema({
    vol.Optional(CONF_PRESENCE): _entity(["input_select", "sensor"]),
    vol.Optional(CONF_BIO): _entity(["input_select", "sensor"]),
    vol.Optional(CONF_DAY): _entity(["input_select", "sensor"]),
    vol.Optional(CONF_MEDIA): _entity(["input_select", "sensor"]),
    vol.Optional(CONF_ENTERTAINMENT): _entity(["binary_sensor", "input_boolean"]),
    vol.Optional(CONF_ACTIVITY): _entity(["input_select", "sensor"]),
    vol.Optional(CONF_ENABLE_CONTROL, default=False): bool,
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(min=5, max=600)),
})


def _device_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CONF_NAME, default=d.get(CONF_NAME, "")): str,
        vol.Required(CONF_SWITCH, default=d.get(CONF_SWITCH)): _entity("switch"),
        vol.Required(CONF_POLICY, default=d.get(CONF_POLICY, "HB")): vol.In(ALL_POLICIES),
        vol.Required(CONF_KIND, default=d.get(CONF_KIND, "generic")): vol.In(ALL_KINDS),
        vol.Optional(CONF_POWER, default=d.get(CONF_POWER)): _entity("sensor"),
        vol.Optional(CONF_BATTERY, default=d.get(CONF_BATTERY)): _entity("sensor"),
        vol.Optional(CONF_ACTIVE_THRESHOLD, default=d.get(CONF_ACTIVE_THRESHOLD, 5.0)): vol.Coerce(float),
        vol.Optional(CONF_IDLE_THRESHOLD, default=d.get(CONF_IDLE_THRESHOLD, 2.0)): vol.Coerce(float),
        vol.Optional(CONF_DEADBAND_LOW, default=d.get(CONF_DEADBAND_LOW)): vol.Any(None, vol.Coerce(float)),
        vol.Optional(CONF_DEADBAND_HIGH, default=d.get(CONF_DEADBAND_HIGH)): vol.Any(None, vol.Coerce(float)),
        vol.Optional(CONF_STABLE_OFF, default=d.get(CONF_STABLE_OFF, 600)): int,
        vol.Optional(CONF_UNKNOWN, default=d.get(CONF_UNKNOWN, UNK_ASSUME_ACTIVE)):
            vol.In([UNK_ASSUME_ACTIVE, UNK_ASSUME_IDLE]),
        vol.Optional(CONF_ALLOWED_CONTEXTS, default=d.get(CONF_ALLOWED_CONTEXTS, [])):
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=["morning", "day", "evening", "night"],
                multiple=True, mode=selector.SelectSelectorMode.LIST,
            )),
        vol.Optional(CONF_NEVER_CUT_ACTIVE, default=d.get(CONF_NEVER_CUT_ACTIVE, True)): bool,
        vol.Optional(CONF_WAKE_SIGNAL_ONLY, default=d.get(CONF_WAKE_SIGNAL_ONLY, False)): bool,
        vol.Optional(CONF_TABLET_LOW, default=d.get(CONF_TABLET_LOW, 40)): int,
        vol.Optional(CONF_TABLET_HIGH, default=d.get(CONF_TABLET_HIGH, 80)): int,
        vol.Optional(CONF_DIFFUSER_ON_MIN, default=d.get(CONF_DIFFUSER_ON_MIN, 15)): int,
        vol.Optional(CONF_DIFFUSER_OFF_MIN, default=d.get(CONF_DIFFUSER_OFF_MIN, 15)): int,
        vol.Optional(CONF_MANUAL_COOLDOWN, default=d.get(CONF_MANUAL_COOLDOWN, 900)): int,
    })


class BenniPlugConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(
                title="Benni Plug Policy",
                data={**user_input, CONF_DEVICES: []},
            )
        return self.async_show_form(step_id="user", data_schema=_GLOBAL_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> "BenniPlugOptionsFlow":
        return BenniPlugOptionsFlow(entry)


class BenniPlugOptionsFlow(OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._working_devices: list[dict] = []

    @property
    def _devices(self) -> list[dict]:
        opts = {**self.entry.data, **self.entry.options}
        return list(opts.get(CONF_DEVICES, []))

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["globals", "add_device", "edit_device", "remove_device"],
        )

    # --- globals ---
    async def async_step_globals(self, user_input=None):
        opts = {**self.entry.data, **self.entry.options}
        if user_input is not None:
            new_opts = {**opts, **user_input}
            new_opts[CONF_DEVICES] = self._devices
            return self.async_create_entry(title="", data=new_opts)
        return self.async_show_form(
            step_id="globals",
            data_schema=vol.Schema({
                vol.Optional(CONF_PRESENCE, default=opts.get(CONF_PRESENCE)): _entity(["input_select", "sensor"]),
                vol.Optional(CONF_BIO, default=opts.get(CONF_BIO)): _entity(["input_select", "sensor"]),
                vol.Optional(CONF_DAY, default=opts.get(CONF_DAY)): _entity(["input_select", "sensor"]),
                vol.Optional(CONF_MEDIA, default=opts.get(CONF_MEDIA)): _entity(["input_select", "sensor"]),
                vol.Optional(CONF_ENTERTAINMENT, default=opts.get(CONF_ENTERTAINMENT)): _entity(["binary_sensor", "input_boolean"]),
                vol.Optional(CONF_ACTIVITY, default=opts.get(CONF_ACTIVITY)): _entity(["input_select", "sensor"]),
                vol.Optional(CONF_ENABLE_CONTROL, default=opts.get(CONF_ENABLE_CONTROL, False)): bool,
                vol.Optional(CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)):
                    vol.All(int, vol.Range(min=5, max=600)),
            }),
        )

    # --- add ---
    async def async_step_add_device(self, user_input=None):
        if user_input is not None:
            user_input["device_id"] = f"dev_{uuid.uuid4().hex[:8]}"
            devices = self._devices + [user_input]
            opts = {**self.entry.data, **self.entry.options, CONF_DEVICES: devices}
            return self.async_create_entry(title="", data=opts)
        return self.async_show_form(step_id="add_device", data_schema=_device_schema())

    # --- edit ---
    async def async_step_edit_device(self, user_input=None):
        devices = self._devices
        if not devices:
            return self.async_abort(reason="no_devices")
        if user_input is not None and "device_id" in user_input and len(user_input) == 1:
            self._editing_id = user_input["device_id"]
            existing = next((d for d in devices if d["device_id"] == self._editing_id), {})
            return self.async_show_form(step_id="edit_device", data_schema=_device_schema(existing))
        if user_input is not None:
            new_devices = []
            for d in devices:
                if d["device_id"] == self._editing_id:
                    merged = {**d, **user_input}
                    new_devices.append(merged)
                else:
                    new_devices.append(d)
            opts = {**self.entry.data, **self.entry.options, CONF_DEVICES: new_devices}
            return self.async_create_entry(title="", data=opts)
        return self.async_show_form(
            step_id="edit_device",
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(
                    {d["device_id"]: d.get(CONF_NAME, d["device_id"]) for d in devices}
                ),
            }),
        )

    # --- remove ---
    async def async_step_remove_device(self, user_input=None):
        devices = self._devices
        if not devices:
            return self.async_abort(reason="no_devices")
        if user_input is not None:
            keep = [d for d in devices if d["device_id"] != user_input["device_id"]]
            opts = {**self.entry.data, **self.entry.options, CONF_DEVICES: keep}
            return self.async_create_entry(title="", data=opts)
        return self.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(
                    {d["device_id"]: d.get(CONF_NAME, d["device_id"]) for d in devices}
                ),
            }),
        )
