"""Config- und Options-Flow-Helfer für Plug Policy Engine.

Single-Instance via unique_id `plug_policy_engine_singleton`.

Add-Flow (1 Schritt `module_step`): globale Selektoren (Presence, Bio, Day,
Media, Entertainment, Activity) + Enable-Control + Scan-Interval; Devices
werden im Options-Flow gepflegt.

Options-Flow als Menü: globals | add_device | edit_device | remove_device.

Add/Edit device ist in drei UX-Schritte aufgeteilt:

1. ``device_basics``  — Name, Schalter, Policy, Geräteart
2. ``device_sensors`` — Sensoren mit Auto-Vorschlag (Leistung, Batterie)
3. ``device_advanced`` — kind/policy-spezifische Schwellen und Verhalten

Engine-Logik und CONF-Keys bleiben unverändert; bestehende Entries
bleiben kompatibel, weil engine.py jeden Key per ``.get`` mit Defaults
liest.
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
from . import _suggest
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
    DEFAULT_ACTIVE_THRESHOLD,
    DEFAULT_DIFFUSER_OFF,
    DEFAULT_DIFFUSER_ON,
    DEFAULT_IDLE_THRESHOLD,
    DEFAULT_MANUAL_COOLDOWN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STABLE_OFF,
    DEFAULT_TABLET_HIGH,
    DEFAULT_TABLET_LOW,
    MODULE_ID,
    NAME,
    UNK_ASSUME_ACTIVE,
    UNK_ASSUME_IDLE,
)


# ---------------------------------------------------------------------------
# Selectors and tiny per-field schema fragments.
# ---------------------------------------------------------------------------


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


# ---- step 1: basics ------------------------------------------------------

def _basics_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CONF_NAME, default=d.get(CONF_NAME, "")): str,
        vol.Required(CONF_SWITCH, default=d.get(CONF_SWITCH)): _entity("switch"),
        vol.Required(CONF_POLICY, default=d.get(CONF_POLICY, "HB")): vol.In(ALL_POLICIES),
        vol.Required(CONF_KIND, default=d.get(CONF_KIND, "generic")): vol.In(ALL_KINDS),
    })


# ---- step 2: sensors (kind-aware) ----------------------------------------

def _sensors_schema(kind: str, defaults: dict | None = None) -> vol.Schema:
    """Render only the sensor slots the kind cares about.

    ``power_entity``/``battery_entity`` defaults are auto-detected from the
    chosen switch slug — they appear pre-filled but the user can clear or
    swap them.
    """
    d = defaults or {}
    schema: dict = {}
    fields = _suggest.sensors_for_kind(kind)
    if "power_entity" in fields:
        schema[vol.Optional(CONF_POWER, default=d.get(CONF_POWER))] = _entity("sensor")
    if "battery_entity" in fields:
        schema[vol.Optional(CONF_BATTERY, default=d.get(CONF_BATTERY))] = _entity("sensor")
    return vol.Schema(schema)


# ---- step 3: advanced (kind/policy-aware) --------------------------------

# Map CONF_* keys to (label-key, schema fragment, default) — only the
# fragment varies; labels live in the translations file.
def _advanced_fragments(d: dict) -> dict[str, tuple]:
    """Return key → (Optional-marker, validator) for every advanced field.

    Looked up by name in `advanced_fields_for_kind`.
    """
    return {
        "active_threshold": (
            vol.Optional(CONF_ACTIVE_THRESHOLD, default=d.get(CONF_ACTIVE_THRESHOLD, DEFAULT_ACTIVE_THRESHOLD)),
            vol.Coerce(float),
        ),
        "idle_threshold": (
            vol.Optional(CONF_IDLE_THRESHOLD, default=d.get(CONF_IDLE_THRESHOLD, DEFAULT_IDLE_THRESHOLD)),
            vol.Coerce(float),
        ),
        "deadband_lower": (
            vol.Optional(CONF_DEADBAND_LOW, default=d.get(CONF_DEADBAND_LOW)),
            vol.Any(None, vol.Coerce(float)),
        ),
        "deadband_upper": (
            vol.Optional(CONF_DEADBAND_HIGH, default=d.get(CONF_DEADBAND_HIGH)),
            vol.Any(None, vol.Coerce(float)),
        ),
        "stable_off_seconds": (
            vol.Optional(CONF_STABLE_OFF, default=d.get(CONF_STABLE_OFF, DEFAULT_STABLE_OFF)),
            vol.All(int, vol.Range(min=0)),
        ),
        "unknown_behavior": (
            vol.Optional(CONF_UNKNOWN, default=d.get(CONF_UNKNOWN, UNK_ASSUME_ACTIVE)),
            vol.In([UNK_ASSUME_ACTIVE, UNK_ASSUME_IDLE]),
        ),
        "never_cut_when_active": (
            vol.Optional(CONF_NEVER_CUT_ACTIVE, default=d.get(CONF_NEVER_CUT_ACTIVE, True)),
            bool,
        ),
        "manual_on_cooldown_seconds": (
            vol.Optional(CONF_MANUAL_COOLDOWN, default=d.get(CONF_MANUAL_COOLDOWN, DEFAULT_MANUAL_COOLDOWN)),
            vol.All(int, vol.Range(min=0)),
        ),
        "wake_signal_only": (
            vol.Optional(CONF_WAKE_SIGNAL_ONLY, default=d.get(CONF_WAKE_SIGNAL_ONLY, False)),
            bool,
        ),
        "tablet_low": (
            vol.Optional(CONF_TABLET_LOW, default=d.get(CONF_TABLET_LOW, DEFAULT_TABLET_LOW)),
            vol.All(int, vol.Range(min=0, max=100)),
        ),
        "tablet_high": (
            vol.Optional(CONF_TABLET_HIGH, default=d.get(CONF_TABLET_HIGH, DEFAULT_TABLET_HIGH)),
            vol.All(int, vol.Range(min=0, max=100)),
        ),
        "diffuser_on_minutes": (
            vol.Optional(CONF_DIFFUSER_ON_MIN, default=d.get(CONF_DIFFUSER_ON_MIN, DEFAULT_DIFFUSER_ON)),
            vol.All(int, vol.Range(min=1)),
        ),
        "diffuser_off_minutes": (
            vol.Optional(CONF_DIFFUSER_OFF_MIN, default=d.get(CONF_DIFFUSER_OFF_MIN, DEFAULT_DIFFUSER_OFF)),
            vol.All(int, vol.Range(min=1)),
        ),
        "allowed_contexts": (
            vol.Optional(CONF_ALLOWED_CONTEXTS, default=d.get(CONF_ALLOWED_CONTEXTS, [])),
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=["morning", "day", "evening", "night"],
                multiple=True, mode=selector.SelectSelectorMode.LIST,
            )),
        ),
    }


def _advanced_schema(kind: str, policy: str, defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    fragments = _advanced_fragments(d)
    fields = _suggest.advanced_fields_for_kind(kind, policy)
    out: dict = {}
    for key in fields:
        if key not in fragments:
            continue
        marker, validator = fragments[key]
        out[marker] = validator
    return vol.Schema(out)


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


def _strip_empty(d: dict) -> dict:
    """Drop None/"" so the engine sees defaults and we don't store noise."""
    return {k: v for k, v in d.items() if v not in (None, "")}


class OptionsFlowHelper:
    """Multi-step add/edit device flow.

    The flow keeps in-progress device data in ``self._draft`` so we can
    walk basics → sensors → advanced without losing state. ``self._editing_id``
    is set for the edit path so the final step writes back into the
    existing device record instead of creating a new one.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow
        self._editing_id: str | None = None
        self._draft: dict[str, Any] = {}

    # ----- helpers ----------------------------------------------------------

    def _devices(self) -> list[dict]:
        opts = {**self.entry.data, **self.entry.options}
        return list(opts.get(CONF_DEVICES, []))

    def _merged_opts(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def _save_devices(self, new_devices: list[dict]) -> FlowResult:
        new_opts = {**self.entry.options, CONF_DEVICES: new_devices}
        new_opts.pop(CONF_MODULE_ID, None)
        # Clear in-flight draft after persisting.
        self._draft = {}
        self._editing_id = None
        return self.flow.async_create_entry(title="", data=new_opts)

    # ----- menu / globals --------------------------------------------------

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.flow.async_show_menu(
            step_id="init",
            menu_options=["globals", "add_device", "edit_device", "remove_device"],
        )

    async def async_step_globals(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        opts = self._merged_opts()
        if user_input is not None:
            new_opts = {**opts, **user_input}
            new_opts[CONF_DEVICES] = self._devices()
            new_opts.pop(CONF_MODULE_ID, None)
            return self.flow.async_create_entry(title="", data=new_opts)
        return self.flow.async_show_form(step_id="globals", data_schema=_globals_schema(opts))

    # ----- add device: basics → sensors → advanced -------------------------

    async def async_step_add_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        # Step 1: basics.
        self._editing_id = None
        if user_input is None:
            self._draft = {}
            return self.flow.async_show_form(
                step_id="device_basics", data_schema=_basics_schema(),
            )
        # User-input on add_device is treated as basics (single-step UI
        # path) — but conventionally `add_device` itself shows the form,
        # and subsequent steps are reached via their own step_ids.
        return self.flow.async_show_form(
            step_id="device_basics", data_schema=_basics_schema(),
        )

    async def async_step_device_basics(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            defaults = self._draft if self._draft else None
            return self.flow.async_show_form(
                step_id="device_basics", data_schema=_basics_schema(defaults),
            )
        # Stash basics in the draft and move to sensors.
        self._draft.update(user_input)
        return await self._show_sensors_step()

    async def _show_sensors_step(self) -> FlowResult:
        kind = self._draft.get(CONF_KIND, "generic")
        # Auto-detect once when the user first reaches this step; never
        # overwrite a value the user typed in the edit flow.
        suggestion = _suggest.suggest_for_switch(self.hass, self._draft.get(CONF_SWITCH))
        defaults: dict[str, Any] = {}
        if self._editing_id:
            existing = next(
                (d for d in self._devices() if d.get("device_id") == self._editing_id),
                {},
            )
            defaults = {
                CONF_POWER: existing.get(CONF_POWER),
                CONF_BATTERY: existing.get(CONF_BATTERY),
            }
        # Only fill from auto-detection if the existing value is empty.
        if not defaults.get(CONF_POWER):
            defaults[CONF_POWER] = suggestion.power_entity
        if not defaults.get(CONF_BATTERY):
            defaults[CONF_BATTERY] = suggestion.battery_entity
        # Preserve anything the user already typed during this draft.
        for k, v in self._draft.items():
            if k in (CONF_POWER, CONF_BATTERY) and v:
                defaults[k] = v
        description = None
        if suggestion.siblings:
            # Show informational hint about voltage/current/energy IDs we
            # spotted on the same slug. Purely cosmetic — engine doesn't
            # use them.
            description = {
                "suggested_power": suggestion.power_entity or "—",
                "suggested_battery": suggestion.battery_entity or "—",
                "siblings": ", ".join(suggestion.siblings),
            }
        return self.flow.async_show_form(
            step_id="device_sensors",
            data_schema=_sensors_schema(kind, defaults),
            description_placeholders=description,
        )

    async def async_step_device_sensors(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return await self._show_sensors_step()
        self._draft.update(_strip_empty(user_input))
        return await self._show_advanced_step()

    async def _show_advanced_step(self) -> FlowResult:
        kind = self._draft.get(CONF_KIND, "generic")
        policy = self._draft.get(CONF_POLICY, "HB")
        defaults: dict[str, Any] = {}
        if self._editing_id:
            existing = next(
                (d for d in self._devices() if d.get("device_id") == self._editing_id),
                {},
            )
            defaults.update(existing)
        defaults.update(self._draft)
        return self.flow.async_show_form(
            step_id="device_advanced",
            data_schema=_advanced_schema(kind, policy, defaults),
        )

    async def async_step_device_advanced(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return await self._show_advanced_step()
        self._draft.update(user_input)
        # Persist.
        cleaned = _strip_empty(self._draft)
        devices = self._devices()
        if self._editing_id:
            new_devices: list[dict] = []
            for d in devices:
                if d.get("device_id") == self._editing_id:
                    # Preserve any keys we don't render so old entries
                    # keep their existing values across an edit.
                    merged = {**d, **cleaned, "device_id": d["device_id"]}
                    new_devices.append(merged)
                else:
                    new_devices.append(d)
            return self._save_devices(new_devices)
        cleaned["device_id"] = f"dev_{uuid.uuid4().hex[:8]}"
        return self._save_devices(devices + [cleaned])

    # ----- edit device -----------------------------------------------------

    async def async_step_edit_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        devices = self._devices()
        if not devices:
            return self.flow.async_abort(reason="no_devices")
        # Selection step.
        if user_input is None or set(user_input) != {"device_id"}:
            return self.flow.async_show_form(
                step_id="edit_device",
                data_schema=vol.Schema({
                    vol.Required("device_id"): vol.In(
                        {d["device_id"]: d.get(CONF_NAME, d["device_id"]) for d in devices}
                    ),
                }),
            )
        # Picked a device → seed draft from it and jump into basics.
        self._editing_id = user_input["device_id"]
        existing = next(
            (d for d in devices if d.get("device_id") == self._editing_id), {}
        )
        self._draft = {
            k: v for k, v in existing.items()
            if k not in ("device_id",)
        }
        return self.flow.async_show_form(
            step_id="device_basics", data_schema=_basics_schema(existing),
        )

    # ----- remove ---------------------------------------------------------

    async def async_step_remove_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        devices = self._devices()
        if not devices:
            return self.flow.async_abort(reason="no_devices")
        if user_input is not None:
            keep = [d for d in devices if d["device_id"] != user_input["device_id"]]
            return self._save_devices(keep)
        return self.flow.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(
                    {d["device_id"]: d.get(CONF_NAME, d["device_id"]) for d in devices}
                ),
            }),
        )
