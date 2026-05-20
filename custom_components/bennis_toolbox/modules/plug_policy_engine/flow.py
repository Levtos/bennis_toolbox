"""Config- und Options-Flow-Helfer für Plug Policy Engine.

Single-Instance via unique_id `plug_policy_engine_singleton`.

Add-Flow (1 Schritt `module_step`): globale Selektoren (Presence, Bio, Day,
Media, Entertainment, Activity) + Enable-Control + Scan-Interval; Devices
werden später im Options-Flow gepflegt.

Options-Flow als Menü: globals | add_device | edit_device | remove_device.
"""
from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ...const import CONF_MODULE_ID
from .const import (
    ALL_KINDS,
    ALL_POLICIES,
    CONF_ACTIVE_THRESHOLD,
    CONF_ACTIVITY,
    CONF_ALLOWED_CONTEXTS,
    CONF_BATTERY,
    CONF_BIO,
    CONF_DAY,
    CONF_DEADBAND_HIGH,
    CONF_DEADBAND_LOW,
    CONF_DEVICES,
    CONF_DIFFUSER_OFF_MIN,
    CONF_DIFFUSER_ON_MIN,
    CONF_ENABLE_CONTROL,
    CONF_ENTERTAINMENT,
    CONF_IDLE_THRESHOLD,
    CONF_KIND,
    CONF_MANUAL_COOLDOWN,
    CONF_MEDIA,
    CONF_NAME,
    CONF_NEVER_CUT_ACTIVE,
    CONF_POLICY,
    CONF_POWER,
    CONF_PRESENCE,
    CONF_SCAN_INTERVAL,
    CONF_STABLE_OFF,
    CONF_SWITCH,
    CONF_TABLET_HIGH,
    CONF_TABLET_LOW,
    CONF_UNKNOWN,
    CONF_WAKE_SIGNAL_ONLY,
    DEFAULT_SCAN_INTERVAL,
    MODULE_ID,
    NAME,
    UNK_ASSUME_ACTIVE,
    UNK_ASSUME_IDLE,
)


def _entity(domain=None) -> selector.EntitySelector:
    cfg: dict = {}
    if domain:
        cfg["domain"] = domain
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


def _globals_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Optional(CONF_PRESENCE, default=d.get(CONF_PRESENCE)): _entity(["input_select", "sensor"]),
        vol.Optional(CONF_BIO, default=d.get(CONF_BIO)): _entity(["input_select", "sensor"]),
        vol.Optional(CONF_DAY, default=d.get(CONF_DAY)): _entity(["input_select", "sensor"]),
        vol.Optional(CONF_MEDIA, default=d.get(CONF_MEDIA)): _entity(["input_select", "sensor"]),
        vol.Optional(CONF_ENTERTAINMENT, default=d.get(CONF_ENTERTAINMENT)):
            _entity(["binary_sensor", "input_boolean"]),
        vol.Optional(CONF_ACTIVITY, default=d.get(CONF_ACTIVITY)): _entity(["input_select", "sensor"]),
        vol.Optional(CONF_ENABLE_CONTROL, default=d.get(CONF_ENABLE_CONTROL, False)): bool,
        vol.Optional(CONF_SCAN_INTERVAL, default=d.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)):
            vol.All(int, vol.Range(min=5, max=600)),
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
        vol.Optional(CONF_ACTIVE_THRESHOLD, default=d.get(CONF_ACTIVE_THRESHOLD, 5.0)):
            vol.Coerce(float),
        vol.Optional(CONF_IDLE_THRESHOLD, default=d.get(CONF_IDLE_THRESHOLD, 2.0)):
            vol.Coerce(float),
        vol.Optional(CONF_DEADBAND_LOW, default=d.get(CONF_DEADBAND_LOW)):
            vol.Any(None, vol.Coerce(float)),
        vol.Optional(CONF_DEADBAND_HIGH, default=d.get(CONF_DEADBAND_HIGH)):
            vol.Any(None, vol.Coerce(float)),
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
            step_id="module_step", data_schema=_globals_schema(),
        )

    async def async_step_module_step(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="module_step", data_schema=_globals_schema(),
            )
        data: dict[str, Any] = {CONF_MODULE_ID: MODULE_ID, CONF_DEVICES: []}
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
        self._editing_id: str | None = None

    def _devices(self) -> list[dict]:
        opts = {**self.entry.data, **self.entry.options}
        return list(opts.get(CONF_DEVICES, []))

    def _merged_opts(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.flow.async_show_menu(
            step_id="init",
            menu_options=["globals", "add_device", "edit_device", "remove_device"],
        )

    # --- globals ---
    async def async_step_globals(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        opts = self._merged_opts()
        if user_input is not None:
            new_opts = {**opts, **user_input}
            new_opts[CONF_DEVICES] = self._devices()
            new_opts.pop(CONF_MODULE_ID, None)
            return self.flow.async_create_entry(title="", data=new_opts)
        return self.flow.async_show_form(step_id="globals", data_schema=_globals_schema(opts))

    # --- add ---
    async def async_step_add_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            user_input["device_id"] = f"dev_{uuid.uuid4().hex[:8]}"
            devices = self._devices() + [user_input]
            new_opts = {**self.entry.options, CONF_DEVICES: devices}
            new_opts.pop(CONF_MODULE_ID, None)
            return self.flow.async_create_entry(title="", data=new_opts)
        return self.flow.async_show_form(step_id="add_device", data_schema=_device_schema())

    # --- edit ---
    async def async_step_edit_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        devices = self._devices()
        if not devices:
            return self.flow.async_abort(reason="no_devices")
        if user_input is not None and "device_id" in user_input and len(user_input) == 1:
            self._editing_id = user_input["device_id"]
            existing = next(
                (d for d in devices if d["device_id"] == self._editing_id), {}
            )
            return self.flow.async_show_form(
                step_id="edit_device", data_schema=_device_schema(existing),
            )
        if user_input is not None:
            new_devices = []
            for d in devices:
                if d["device_id"] == self._editing_id:
                    new_devices.append({**d, **user_input})
                else:
                    new_devices.append(d)
            new_opts = {**self.entry.options, CONF_DEVICES: new_devices}
            new_opts.pop(CONF_MODULE_ID, None)
            return self.flow.async_create_entry(title="", data=new_opts)
        return self.flow.async_show_form(
            step_id="edit_device",
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(
                    {d["device_id"]: d.get(CONF_NAME, d["device_id"]) for d in devices}
                ),
            }),
        )

    # --- remove ---
    async def async_step_remove_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        devices = self._devices()
        if not devices:
            return self.flow.async_abort(reason="no_devices")
        if user_input is not None:
            keep = [d for d in devices if d["device_id"] != user_input["device_id"]]
            new_opts = {**self.entry.options, CONF_DEVICES: keep}
            new_opts.pop(CONF_MODULE_ID, None)
            return self.flow.async_create_entry(title="", data=new_opts)
        return self.flow.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(
                    {d["device_id"]: d.get(CONF_NAME, d["device_id"]) for d in devices}
                ),
            }),
        )
