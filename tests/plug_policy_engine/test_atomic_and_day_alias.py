"""Two Einhornzentrale-specific tweaks:

1. Auto-detection prefers `_power_atomic` over the raw `_power` sensor
   so devices in the lab default to the smoothed aggregator entity.
   Raw remains as fallback; an explicit user value is never replaced.

2. Detailed day-state values from `sensor.context_day_state_combined`
   (early_morning, late_morning, forenoon, afternoon, early_evening,
   late_evening, early_night, late_night) are folded into the coarse
   morning/day/evening/night vocabulary the engine compares
   `allowed_contexts` against. Existing morning/day/evening/night
   values continue to work unchanged.
"""
from __future__ import annotations

import sys
import types

import pytest


# Reuse the loader-driven stubs set up by the smoke test.
import tests.plug_policy_engine.test_module_smoke as smoke  # noqa: E402
from tests.plug_policy_engine.test_device_ux import (  # noqa: E402
    _FakeFlow, _FakeEntry, _FakeHass, _schema_keys,
)

flow_module = smoke.flow_module
suggest_module = sys.modules["pp_suggest"]

# Pure engine + const are already loaded by the conftest:
import pp_engine as engine  # noqa: E402
import pp_const as const  # noqa: E402


# ---------------------------------------------------------------------------
# 1) Auto-detection: atomic > raw > active_power > power_w
# ---------------------------------------------------------------------------


def test_atomic_power_is_preferred_over_raw_power():
    hass = _FakeHass([
        "sensor.living_pc_plug_power",
        "sensor.living_pc_plug_power_atomic",
    ])
    s = suggest_module.suggest_for_switch(hass, "switch.living_pc_plug")
    assert s.power_entity == "sensor.living_pc_plug_power_atomic"


def test_raw_power_is_used_when_atomic_absent():
    hass = _FakeHass(["sensor.living_pc_plug_power"])
    s = suggest_module.suggest_for_switch(hass, "switch.living_pc_plug")
    assert s.power_entity == "sensor.living_pc_plug_power"


def test_atomic_battery_is_preferred_over_raw_battery():
    hass = _FakeHass([
        "sensor.bedroom_tablet_plug_battery",
        "sensor.bedroom_tablet_plug_battery_atomic",
    ])
    s = suggest_module.suggest_for_switch(hass, "switch.bedroom_tablet_plug")
    assert s.battery_entity == "sensor.bedroom_tablet_plug_battery_atomic"


def test_power_priority_order_is_canonical():
    """When all four candidates exist, the priority list is strict."""
    hass = _FakeHass([
        "sensor.x_power_w",
        "sensor.x_active_power",
        "sensor.x_power",
        "sensor.x_power_atomic",
    ])
    s = suggest_module.suggest_for_switch(hass, "switch.x")
    assert s.power_entity == "sensor.x_power_atomic"


# Edit flow keeps an existing manual/raw value even if the atomic
# sister exists in HA — auto-detection only fills empty slots.

import asyncio
from functools import wraps


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


@_run
async def test_edit_flow_keeps_raw_power_when_atomic_now_exists():
    """User originally picked the raw sensor; later they install the
    atomic aggregator. The edit flow must surface the raw sensor as the
    field default, not silently swap it for atomic."""
    existing = {
        "device_id": "dev_xyz", "name": "PC",
        "switch_entity": "switch.living_pc_plug",
        "policy": "HB", "kind": "pc",
        "power_entity": "sensor.living_pc_plug_power",  # raw, on purpose
    }
    hass = _FakeHass([
        "sensor.living_pc_plug_power",
        "sensor.living_pc_plug_power_atomic",
    ])
    entry = _FakeEntry(options={"devices": [existing]})
    flow = _FakeFlow()
    helper = flow_module.OptionsFlowHelper(hass, entry, flow)
    await helper.async_step_edit_device()
    await helper.async_step_edit_device({"device_id": "dev_xyz"})
    await helper.async_step_device_basics({
        "name": "PC", "switch_entity": "switch.living_pc_plug",
        "policy": "HB", "kind": "pc",
    })
    sensors_form_schema = flow.last_form["schema"]
    found = None
    for marker in sensors_form_schema.schema:
        if str(getattr(marker, "schema", marker)) == "power_entity":
            found = marker.default()
            break
    assert found == "sensor.living_pc_plug_power"


# ---------------------------------------------------------------------------
# 2) Day-phase aliasing in the engine.
# ---------------------------------------------------------------------------


def _make_cfg(allowed: list[str] | None = None):
    return engine.DeviceConfig(
        device_id="d",
        name="Diffuser",
        switch_entity="switch.x",
        policy=const.POLICY_SC,
        kind=const.KIND_GENERIC,
        active_threshold=5.0,
        idle_threshold=2.0,
        allowed_contexts=list(allowed or []),
    )


def _make_state(switch_state: str = "off"):
    return engine.DeviceState(switch_state=switch_state, power_w=0.0)


def _make_ctx(day_phase: str | None):
    return engine.GlobalContext(
        presence=const.PRESENCE_HOME,
        bio=const.BIO_AWAKE,
        day_phase=day_phase,
        now_ts=1_700_000_000.0,
    )


def test_normalise_day_phase_maps_detailed_to_coarse():
    f = engine._normalise_day_phase
    assert f("early_morning") == "morning"
    assert f("late_morning") == "morning"
    assert f("forenoon") == "morning"
    assert f("afternoon") == "day"
    assert f("early_evening") == "evening"
    assert f("late_evening") == "evening"
    assert f("early_night") == "night"
    assert f("late_night") == "night"


def test_normalise_day_phase_passthrough_for_coarse_and_unknown():
    f = engine._normalise_day_phase
    # Coarse vocabulary unchanged.
    for v in ("morning", "day", "evening", "night"):
        assert f(v) == v
    # Unknown strings pass through (don't lose information).
    assert f("custom_phase") == "custom_phase"
    assert f(None) is None
    # Case folding to lowercase before lookup, but original returned
    # unchanged if no alias matches.
    assert f("LATE_MORNING") == "morning"


def test_sc_allowed_morning_matches_late_morning_input():
    decision = engine.evaluate(
        _make_cfg(allowed=["morning"]),
        _make_state(switch_state="off"),
        _make_ctx("late_morning"),
    )
    # Within allowed phase + home + awake → desired ON.
    assert decision.desired_switch_state == const.DESIRED_ON
    # The snapshot records the normalised phase.
    assert decision.context["day_phase"] == "morning"


def test_sc_allowed_evening_matches_late_evening_input():
    decision = engine.evaluate(
        _make_cfg(allowed=["evening"]),
        _make_state(switch_state="off"),
        _make_ctx("late_evening"),
    )
    assert decision.desired_switch_state == const.DESIRED_ON


def test_sc_allowed_night_matches_early_night_input():
    decision = engine.evaluate(
        _make_cfg(allowed=["night"]),
        _make_state(switch_state="off"),
        _make_ctx("early_night"),
    )
    assert decision.desired_switch_state == const.DESIRED_ON


def test_sc_existing_coarse_values_still_work():
    """Backwards-compatibility regression: morning/day/evening/night
    values stored on existing entries continue to match exactly."""
    for coarse in ("morning", "day", "evening", "night"):
        decision = engine.evaluate(
            _make_cfg(allowed=[coarse]),
            _make_state(switch_state="off"),
            _make_ctx(coarse),
        )
        assert decision.desired_switch_state == const.DESIRED_ON, coarse


def test_sc_outside_allowed_phase_after_normalisation_still_blocks():
    """`afternoon` folds to `day`, so a config allowing only `morning`
    must NOT match — the normalisation isn't a free pass."""
    decision = engine.evaluate(
        _make_cfg(allowed=["morning"]),
        _make_state(switch_state="off"),
        _make_ctx("afternoon"),
    )
    assert decision.desired_switch_state != const.DESIRED_ON
