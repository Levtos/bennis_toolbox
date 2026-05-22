"""UX-Tests für den Multi-Step Add/Edit Device Flow.

Deckt ab:
- Auto-Detection: `switch.living_pc_plug` → `sensor.living_pc_plug_power`.
- Defensive Fallbacks: kein Power-Sensor → Feld bleibt leer, Flow läuft.
- Kind-gefilterte Advanced-Felder: pc/tablet/diffuser zeigen je das
  Richtige.
- Edit-Flow: bestehende Werte werden erhalten, Auto-Detection nur
  defensiv (überschreibt nichts).
- Existing Config Entries bleiben kompatibel (ungerenderte Keys
  überleben einen Edit).

Engine-Logik wird nicht angefasst — alle Defaults landen weiter in
``engine.py`` über `.get`.
"""
from __future__ import annotations

import asyncio
import sys
import types
from functools import wraps

import pytest


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# Reuse the module loader set up by test_module_smoke.py — that file
# imports first alphabetically and installs all the HA + toolbox stubs.
import tests.plug_policy_engine.test_module_smoke as smoke  # noqa: E402

flow_module = smoke.flow_module
suggest_module = sys.modules["pp_suggest"]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeStates:
    """Minimal `hass.states` that supports async_entity_ids('sensor')."""

    def __init__(self, sensor_ids: list[str]) -> None:
        self._sensors = list(sensor_ids)

    def async_entity_ids(self, domain: str | None = None):
        if domain is None:
            return list(self._sensors)
        if domain == "sensor":
            return list(self._sensors)
        return []


class _FakeHass:
    def __init__(self, sensors: list[str] | None = None) -> None:
        self.states = _FakeStates(sensors or [])
        self.data = {"bennis_toolbox": {"entries": {}}}


class _FakeEntry:
    def __init__(self, data=None, options=None):
        self.data = data or {}
        self.options = options or {}
        self.entry_id = "entry-1"


class _FakeFlow:
    """Captures form/menu/create-entry calls so tests can assert
    step-by-step navigation."""

    def __init__(self) -> None:
        self.last_form: dict | None = None
        self.last_menu: dict | None = None
        self.created_entry: dict | None = None

    def async_show_form(self, step_id, data_schema=None, description_placeholders=None, **_kw):
        self.last_form = {
            "step_id": step_id,
            "schema": data_schema,
            "description": description_placeholders,
        }
        return {"type": "form", "step_id": step_id}

    def async_show_menu(self, step_id, menu_options=None):
        self.last_menu = {"step_id": step_id, "options": list(menu_options or [])}
        return {"type": "menu", "step_id": step_id}

    def async_create_entry(self, title, data, options=None):
        self.created_entry = {
            "title": title,
            "data": dict(data),
            "options": dict(options or {}),
        }
        return self.created_entry

    def async_abort(self, reason):
        return {"type": "abort", "reason": reason}


def _schema_keys(schema) -> set[str]:
    """Pull CONF-key names from a voluptuous Schema regardless of marker."""
    out: set[str] = set()
    for key in schema.schema:
        name = getattr(key, "schema", key)
        out.add(str(name))
    return out


# ---------------------------------------------------------------------------
# 1) Pure suggestion helper.
# ---------------------------------------------------------------------------


def test_base_slug_strips_domain():
    assert suggest_module.base_slug("switch.living_pc_plug") == "living_pc_plug"
    assert suggest_module.base_slug("living_pc_plug") == "living_pc_plug"
    assert suggest_module.base_slug("") is None
    assert suggest_module.base_slug(None) is None


def test_suggest_picks_canonical_power_sibling():
    hass = _FakeHass([
        "sensor.living_pc_plug_power",
        "sensor.living_pc_plug_voltage",
        "sensor.living_pc_plug_current",
        "sensor.living_pc_plug_energy",
        "sensor.other_thing",
    ])
    s = suggest_module.suggest_for_switch(hass, "switch.living_pc_plug")
    assert s.power_entity == "sensor.living_pc_plug_power"
    assert s.battery_entity is None
    assert "sensor.living_pc_plug_voltage" in s.siblings
    assert "sensor.living_pc_plug_current" in s.siblings


def test_suggest_falls_back_to_active_power_when_canonical_missing():
    hass = _FakeHass(["sensor.living_pc_plug_active_power"])
    s = suggest_module.suggest_for_switch(hass, "switch.living_pc_plug")
    assert s.power_entity == "sensor.living_pc_plug_active_power"


def test_suggest_returns_empty_when_no_match():
    hass = _FakeHass(["sensor.totally_unrelated"])
    s = suggest_module.suggest_for_switch(hass, "switch.living_pc_plug")
    assert s.power_entity is None
    assert s.battery_entity is None
    assert s.siblings == ()


def test_suggest_finds_battery_for_tablet():
    hass = _FakeHass([
        "sensor.bedroom_tablet_plug_power",
        "sensor.bedroom_tablet_plug_battery",
    ])
    s = suggest_module.suggest_for_switch(hass, "switch.bedroom_tablet_plug")
    assert s.power_entity == "sensor.bedroom_tablet_plug_power"
    assert s.battery_entity == "sensor.bedroom_tablet_plug_battery"


# ---------------------------------------------------------------------------
# 2) Kind-aware field visibility.
# ---------------------------------------------------------------------------


def test_pc_kind_hides_tablet_and_diffuser_fields():
    fields = suggest_module.advanced_fields_for_kind("pc", "HB")
    assert "active_threshold" in fields
    assert "idle_threshold" in fields
    assert "tablet_low" not in fields
    assert "diffuser_on_minutes" not in fields
    assert "wake_signal_only" not in fields  # pc != h14_dock


def test_tablet_kind_shows_battery_fields_only():
    fields = suggest_module.advanced_fields_for_kind("tablet", "HB")
    assert "tablet_low" in fields and "tablet_high" in fields
    assert "active_threshold" not in fields
    assert "diffuser_on_minutes" not in fields


def test_diffuser_kind_shows_diffuser_timing_fields():
    fields = suggest_module.advanced_fields_for_kind("diffuser", "HB")
    assert "diffuser_on_minutes" in fields and "diffuser_off_minutes" in fields
    assert "active_threshold" not in fields


def test_h14_dock_includes_wake_signal_only():
    fields = suggest_module.advanced_fields_for_kind("h14_dock", "HB")
    assert "wake_signal_only" in fields
    assert "active_threshold" in fields


def test_allowed_contexts_only_for_sc_policy():
    assert "allowed_contexts" not in suggest_module.advanced_fields_for_kind("pc", "HB")
    assert "allowed_contexts" in suggest_module.advanced_fields_for_kind("pc", "SC")


def test_sensors_step_includes_battery_only_for_tablet():
    assert suggest_module.sensors_for_kind("pc") == ("power_entity",)
    assert "battery_entity" in suggest_module.sensors_for_kind("tablet")


# ---------------------------------------------------------------------------
# 3) Multi-step Add Device flow.
# ---------------------------------------------------------------------------


@_run
async def test_add_device_basics_step_shows_only_basic_fields():
    hass = _FakeHass()
    entry = _FakeEntry()
    flow = _FakeFlow()
    helper = flow_module.OptionsFlowHelper(hass, entry, flow)
    await helper.async_step_add_device()
    assert flow.last_form["step_id"] == "device_basics"
    keys = _schema_keys(flow.last_form["schema"])
    assert keys == {"name", "switch_entity", "policy", "kind"}


@_run
async def test_add_device_pc_skips_battery_sensor_step():
    hass = _FakeHass([
        "sensor.living_pc_plug_power",
        "sensor.living_pc_plug_voltage",
    ])
    flow = _FakeFlow()
    helper = flow_module.OptionsFlowHelper(hass, _FakeEntry(), flow)
    # Step 1: basics.
    await helper.async_step_add_device()
    # Step 2: submit basics → expect sensors form auto-filled.
    await helper.async_step_device_basics({
        "name": "PC", "switch_entity": "switch.living_pc_plug",
        "policy": "HB", "kind": "pc",
    })
    assert flow.last_form["step_id"] == "device_sensors"
    keys = _schema_keys(flow.last_form["schema"])
    assert keys == {"power_entity"}  # tablet-only "battery_entity" hidden
    # The suggestion is surfaced via description placeholders so the user
    # sees what was auto-detected.
    assert flow.last_form["description"]["suggested_power"] == "sensor.living_pc_plug_power"


@_run
async def test_add_device_tablet_includes_battery_sensor_field():
    hass = _FakeHass([
        "sensor.bedroom_tablet_plug_power",
        "sensor.bedroom_tablet_plug_battery",
    ])
    flow = _FakeFlow()
    helper = flow_module.OptionsFlowHelper(hass, _FakeEntry(), flow)
    await helper.async_step_add_device()
    await helper.async_step_device_basics({
        "name": "Tablet", "switch_entity": "switch.bedroom_tablet_plug",
        "policy": "HB", "kind": "tablet",
    })
    keys = _schema_keys(flow.last_form["schema"])
    assert keys == {"power_entity", "battery_entity"}


@_run
async def test_add_device_pc_advanced_step_filters_to_power_fields():
    hass = _FakeHass(["sensor.living_pc_plug_power"])
    flow = _FakeFlow()
    helper = flow_module.OptionsFlowHelper(hass, _FakeEntry(), flow)
    await helper.async_step_add_device()
    await helper.async_step_device_basics({
        "name": "PC", "switch_entity": "switch.living_pc_plug",
        "policy": "HB", "kind": "pc",
    })
    await helper.async_step_device_sensors({"power_entity": "sensor.living_pc_plug_power"})
    assert flow.last_form["step_id"] == "device_advanced"
    keys = _schema_keys(flow.last_form["schema"])
    # PC kind, HB policy → power-thresholds family, no tablet/diffuser fields.
    assert "active_threshold" in keys
    assert "tablet_low" not in keys
    assert "diffuser_on_minutes" not in keys


@_run
async def test_add_device_persists_only_filled_fields():
    """No sensors detected → power_entity field is left empty, but the
    flow still completes and stores the device with sensible defaults."""
    hass = _FakeHass([])  # no matching sensors
    entry = _FakeEntry(options={"devices": []})
    flow = _FakeFlow()
    helper = flow_module.OptionsFlowHelper(hass, entry, flow)
    await helper.async_step_add_device()
    await helper.async_step_device_basics({
        "name": "Coffee", "switch_entity": "switch.kitchen_coffee_plug",
        "policy": "HB", "kind": "coffee_maker",
    })
    await helper.async_step_device_sensors({})  # nothing typed
    await helper.async_step_device_advanced({
        "active_threshold": 50.0, "idle_threshold": 5.0,
        "stable_off_seconds": 600, "unknown_behavior": "assume_active",
        "never_cut_when_active": True, "manual_on_cooldown_seconds": 900,
    })
    assert flow.created_entry is not None
    devices = flow.created_entry["data"]["devices"]
    assert len(devices) == 1
    dev = devices[0]
    assert dev["name"] == "Coffee"
    assert dev["switch_entity"] == "switch.kitchen_coffee_plug"
    assert dev["kind"] == "coffee_maker"
    assert "power_entity" not in dev  # never stored when empty
    assert dev["active_threshold"] == 50.0
    assert dev["device_id"].startswith("dev_")


# ---------------------------------------------------------------------------
# 4) Edit flow keeps existing values and survives unknown legacy keys.
# ---------------------------------------------------------------------------


@_run
async def test_edit_device_seeds_basics_with_existing_values():
    existing = {
        "device_id": "dev_xyz",
        "name": "PC",
        "switch_entity": "switch.living_pc_plug",
        "policy": "HB",
        "kind": "pc",
        "power_entity": "sensor.living_pc_plug_power",
        "active_threshold": 42.0,
        # Legacy / future key the current UI doesn't render — must be
        # preserved across the edit:
        "legacy_field_we_dont_render": "keep_me",
    }
    hass = _FakeHass(["sensor.living_pc_plug_power"])
    entry = _FakeEntry(options={"devices": [existing]})
    flow = _FakeFlow()
    helper = flow_module.OptionsFlowHelper(hass, entry, flow)

    # 1) Selection step.
    await helper.async_step_edit_device()
    # 2) Pick device.
    await helper.async_step_edit_device({"device_id": "dev_xyz"})
    assert flow.last_form["step_id"] == "device_basics"

    # 3) Walk basics → sensors → advanced unchanged.
    await helper.async_step_device_basics({
        "name": "PC", "switch_entity": "switch.living_pc_plug",
        "policy": "HB", "kind": "pc",
    })
    await helper.async_step_device_sensors(
        {"power_entity": "sensor.living_pc_plug_power"}
    )
    await helper.async_step_device_advanced({
        "active_threshold": 42.0, "idle_threshold": 2.0,
        "stable_off_seconds": 600, "unknown_behavior": "assume_active",
        "never_cut_when_active": True, "manual_on_cooldown_seconds": 900,
    })
    # The same device_id is reused.
    devices = flow.created_entry["data"]["devices"]
    assert len(devices) == 1
    assert devices[0]["device_id"] == "dev_xyz"
    # Legacy key survives — engine-side compatibility guaranteed.
    assert devices[0]["legacy_field_we_dont_render"] == "keep_me"


@_run
async def test_edit_flow_does_not_overwrite_explicit_power_with_suggestion():
    """If the user already set `power_entity` on the existing device, the
    edit-flow's sensors step must keep that value as the default — auto-
    detection only fills empty slots."""
    existing = {
        "device_id": "dev_xyz", "name": "PC",
        "switch_entity": "switch.living_pc_plug",
        "policy": "HB", "kind": "pc",
        "power_entity": "sensor.custom_power_meter",
    }
    # HA *also* has the canonical sister sensor — make sure we don't pick it.
    hass = _FakeHass([
        "sensor.living_pc_plug_power",
        "sensor.custom_power_meter",
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
    # The shown form's default for power_entity must be the user's value,
    # not the suggestion.
    sensors_form_schema = flow.last_form["schema"]
    # Find the Optional marker for power_entity and inspect its default.
    found_default = None
    for marker in sensors_form_schema.schema:
        if str(getattr(marker, "schema", marker)) == "power_entity":
            found_default = marker.default()
            break
    assert found_default == "sensor.custom_power_meter"
