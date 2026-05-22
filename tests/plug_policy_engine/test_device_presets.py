"""Regression tests for Einhornzentrale device presets.

The flow auto-applies safe defaults for known plug roles when the user
picks a switch in the add path. Presets must:
- set `kind` to the canonical role,
- pre-fill power thresholds, deadband, unknown_behavior, never_cut and
  wake_signal_only,
- never overwrite a value the user typed in this draft or saved on a
  previous edit,
- surface a "Preset detected: …" hint via description_placeholders.

Engine logic is not touched — presets only seed the flow's draft.
"""
from __future__ import annotations

import asyncio
import sys
from functools import wraps

import pytest

import tests.plug_policy_engine.test_module_smoke as smoke  # noqa: E402
from tests.plug_policy_engine.test_device_ux import (  # noqa: E402
    _FakeFlow, _FakeEntry, _FakeHass, _schema_keys,
)

flow_module = smoke.flow_module
suggest_module = sys.modules["pp_suggest"]


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


def _default_for(schema, name):
    for marker in schema.schema:
        if str(getattr(marker, "schema", marker)) == name:
            try:
                return marker.default()
            except Exception:
                return None
    return None


# ---------------------------------------------------------------------------
# 1) Raw preset lookup.
# ---------------------------------------------------------------------------


def test_preset_for_switch_returns_pc_safe_defaults():
    p = suggest_module.preset_for_switch("switch.living_pc_plug")
    assert p is not None and p.values["kind"] == "pc"
    assert p.values["active_threshold"] == 20.0
    assert p.values["idle_threshold"] == 8.0
    assert p.values["unknown_behavior"] == "assume_active"


def test_preset_for_switch_returns_none_for_unknown_slug():
    assert suggest_module.preset_for_switch("switch.totally_unknown_thing") is None
    assert suggest_module.preset_for_switch(None) is None
    assert suggest_module.preset_for_switch("") is None


def test_preset_for_appliance_plugs_uses_appliance_kind():
    for slug in (
        "kitchen_washing_machine_plug",
        "kitchen_dryer_plug",
        "kitchen_dishwasher_plug",
    ):
        p = suggest_module.preset_for_switch(f"switch.{slug}")
        assert p is not None
        assert p.values["kind"] == "appliance"
        assert p.values["unknown_behavior"] == "assume_active"


def test_subwoofer_preset_keeps_thresholds_zero_and_protects_unknown():
    p = suggest_module.preset_for_switch("switch.living_subwoofer_plug")
    assert p is not None
    assert p.values["active_threshold"] == 0.0
    assert p.values["idle_threshold"] == 0.0
    assert p.values["deadband_lower"] is None
    assert p.values["deadband_upper"] is None
    # No power sensor → must protect on unknown.
    assert p.values["unknown_behavior"] == "assume_active"


# ---------------------------------------------------------------------------
# 2) Add flow: presets seed kind + advanced defaults.
# ---------------------------------------------------------------------------


async def _walk_add(helper, *, switch: str, name: str, kind: str | None = None,
                   policy: str = "HB", sensors: dict | None = None):
    """Run basics → sensors → advanced; return the advanced-step form."""
    await helper.async_step_add_device()
    basics = {
        "name": name,
        "switch_entity": switch,
        "policy": policy,
        "kind": kind or "generic",
    }
    await helper.async_step_device_basics(basics)
    # Capture the sensors form so callers can introspect it before submitting.
    sensors_form = helper.flow.last_form
    await helper.async_step_device_sensors(sensors or {})
    return sensors_form, helper.flow.last_form


@_run
async def test_add_flow_pc_plug_sets_kind_and_pc_thresholds():
    hass = _FakeHass(["sensor.living_pc_plug_power_atomic"])
    helper = flow_module.OptionsFlowHelper(hass, _FakeEntry(), _FakeFlow())
    sensors_form, advanced_form = await _walk_add(
        helper, switch="switch.living_pc_plug", name="PC",
    )
    # Sensors step description carries the preset hint.
    assert "PC safe defaults" in sensors_form["description"]["preset"]
    # Advanced form defaults reflect the preset.
    schema = advanced_form["schema"]
    assert _default_for(schema, "active_threshold") == 20.0
    assert _default_for(schema, "idle_threshold") == 8.0
    assert _default_for(schema, "deadband_lower") == 8.0
    assert _default_for(schema, "deadband_upper") == 20.0
    assert _default_for(schema, "unknown_behavior") == "assume_active"
    assert _default_for(schema, "never_cut_when_active") is True
    # And the draft itself was upgraded from generic → pc.
    assert helper._draft["kind"] == "pc"


@_run
async def test_add_flow_switch_plug_sets_low_thresholds_and_assume_idle():
    hass = _FakeHass([])
    helper = flow_module.OptionsFlowHelper(hass, _FakeEntry(), _FakeFlow())
    _, advanced_form = await _walk_add(
        helper, switch="switch.living_switch_plug", name="Switch",
    )
    schema = advanced_form["schema"]
    assert _default_for(schema, "active_threshold") == 3.0
    assert _default_for(schema, "idle_threshold") == 1.0
    assert _default_for(schema, "unknown_behavior") == "assume_idle"
    assert helper._draft["kind"] == "generic"


@_run
async def test_add_flow_denon_plug_adopts_denon_kind():
    hass = _FakeHass([])
    helper = flow_module.OptionsFlowHelper(hass, _FakeEntry(), _FakeFlow())
    sensors_form, advanced_form = await _walk_add(
        helper, switch="switch.living_denon_plug", name="Denon",
    )
    assert "Denon" in sensors_form["description"]["preset"]
    assert helper._draft["kind"] == "denon"
    assert _default_for(advanced_form["schema"], "active_threshold") == 8.0


@_run
async def test_add_flow_appliance_plug_adopts_appliance_kind():
    hass = _FakeHass([])
    helper = flow_module.OptionsFlowHelper(hass, _FakeEntry(), _FakeFlow())
    _, advanced_form = await _walk_add(
        helper, switch="switch.kitchen_washing_machine_plug", name="Waschmaschine",
    )
    assert helper._draft["kind"] == "appliance"
    assert _default_for(advanced_form["schema"], "unknown_behavior") == "assume_active"


@_run
async def test_add_flow_coffee_machine_sets_coffee_kind_and_wake_signal_only():
    hass = _FakeHass([])
    helper = flow_module.OptionsFlowHelper(hass, _FakeEntry(), _FakeFlow())
    _, advanced_form = await _walk_add(
        helper, switch="switch.kitchen_coffee_machine_plug", name="Kaffeemaschine",
    )
    assert helper._draft["kind"] == "coffee_maker"
    # wake_signal_only is a coffee-machine-specific flag that the preset enables.
    # The advanced step for coffee_maker uses the common power family (no
    # wake_signal_only field — that's h14_dock-only), but the value is still
    # stashed in the draft for the engine to read.
    assert helper._draft["wake_signal_only"] is True


@_run
async def test_add_flow_subwoofer_keeps_assume_active_when_no_power_entity():
    hass = _FakeHass([])  # no sister sensors
    helper = flow_module.OptionsFlowHelper(hass, _FakeEntry(), _FakeFlow())
    _, advanced_form = await _walk_add(
        helper, switch="switch.living_subwoofer_plug", name="Subwoofer",
    )
    schema = advanced_form["schema"]
    # Zero thresholds, no deadband, protect on unknown.
    assert _default_for(schema, "active_threshold") == 0.0
    assert _default_for(schema, "idle_threshold") == 0.0
    assert _default_for(schema, "deadband_lower") is None
    assert _default_for(schema, "deadband_upper") is None
    assert _default_for(schema, "unknown_behavior") == "assume_active"
    assert _default_for(schema, "never_cut_when_active") is True


# ---------------------------------------------------------------------------
# 3) Preset + atomic power suggestion cooperate.
# ---------------------------------------------------------------------------


@_run
async def test_atomic_power_suggestion_still_wins_over_raw_with_preset():
    hass = _FakeHass([
        "sensor.living_pc_plug_power",
        "sensor.living_pc_plug_power_atomic",
    ])
    helper = flow_module.OptionsFlowHelper(hass, _FakeEntry(), _FakeFlow())
    sensors_form, _ = await _walk_add(
        helper, switch="switch.living_pc_plug", name="PC",
    )
    assert sensors_form["description"]["suggested_power"] == "sensor.living_pc_plug_power_atomic"
    # Preset hint still rendered alongside the sensor suggestion.
    assert "PC safe defaults" in sensors_form["description"]["preset"]


# ---------------------------------------------------------------------------
# 4) Edit flow leaves saved values + hidden legacy keys alone.
# ---------------------------------------------------------------------------


@_run
async def test_edit_flow_does_not_apply_preset_over_existing_values():
    """User saved a PC plug device with non-default thresholds; the
    edit flow must preserve those, not silently overwrite with the
    preset's canonical defaults."""
    existing = {
        "device_id": "dev_pc", "name": "PC",
        "switch_entity": "switch.living_pc_plug",
        "policy": "HB", "kind": "pc",
        "active_threshold": 12.0,  # custom — must survive the edit.
        "idle_threshold": 4.0,
        "unknown_behavior": "assume_idle",
        "_legacy_field": "keep_me",
    }
    hass = _FakeHass(["sensor.living_pc_plug_power_atomic"])
    entry = _FakeEntry(options={"devices": [existing]})
    helper = flow_module.OptionsFlowHelper(hass, entry, _FakeFlow())

    # Selection step.
    await helper.async_step_edit_device()
    await helper.async_step_edit_device({"device_id": "dev_pc"})
    await helper.async_step_device_basics({
        "name": "PC", "switch_entity": "switch.living_pc_plug",
        "policy": "HB", "kind": "pc",
    })
    sensors_form = helper.flow.last_form
    # Edit flow surfaces "generic defaults" — preset is hint-only on add.
    assert "Kein bekanntes Preset" in sensors_form["description"]["preset"]

    await helper.async_step_device_sensors({})
    advanced_form = helper.flow.last_form
    schema = advanced_form["schema"]
    assert _default_for(schema, "active_threshold") == 12.0
    assert _default_for(schema, "idle_threshold") == 4.0
    assert _default_for(schema, "unknown_behavior") == "assume_idle"

    await helper.async_step_device_advanced({
        "active_threshold": 12.0, "idle_threshold": 4.0,
        "stable_off_seconds": 600, "unknown_behavior": "assume_idle",
        "never_cut_when_active": True, "manual_on_cooldown_seconds": 900,
    })
    devices = helper.flow.created_entry["data"]["devices"]
    saved = devices[0]
    assert saved["active_threshold"] == 12.0
    assert saved["unknown_behavior"] == "assume_idle"
    # Legacy key survives — forward/backward compat.
    assert saved["_legacy_field"] == "keep_me"
    # device_id reused, no duplicates.
    assert len(devices) == 1
    assert saved["device_id"] == "dev_pc"


# ---------------------------------------------------------------------------
# 5) Unknown plug → generic defaults + neutral hint.
# ---------------------------------------------------------------------------


@_run
async def test_unknown_plug_shows_generic_defaults_and_neutral_hint():
    hass = _FakeHass([])
    helper = flow_module.OptionsFlowHelper(hass, _FakeEntry(), _FakeFlow())
    sensors_form, advanced_form = await _walk_add(
        helper, switch="switch.guest_room_unknown_plug", name="Misc",
    )
    assert "Kein bekanntes Preset" in sensors_form["description"]["preset"]
    schema = advanced_form["schema"]
    # Fall back to module-level defaults (active=5.0, idle=2.0 per const.py).
    assert _default_for(schema, "active_threshold") == 5.0
    assert _default_for(schema, "idle_threshold") == 2.0
