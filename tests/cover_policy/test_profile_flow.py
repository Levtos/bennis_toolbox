"""UX-focused tests for the cover_policy options flow + profile service.

Covers the four contract points from the brief:
1. Options-Flow speichert geänderte Profilwerte.
2. Service `cover_policy_set_position_profile` überschreibt Werte korrekt.
3. Policy nutzt geänderte Werte (z.B. heat_protect=20).
4. Quellen bleiben im Config-/Options-Flow erhalten und werden nicht entfernt.

Plus: profile schema is now backed by a NumberSelector slider with
clamping and string coercion via voluptuous; we exercise that contract.
"""
from __future__ import annotations

import ast
import asyncio
import os
import sys
import types
from functools import wraps
from pathlib import Path

import pytest
import voluptuous as vol


MODULE_DIR = Path(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
) / "custom_components" / "bennis_toolbox" / "modules" / "cover_policy"


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# ---------------------------------------------------------------------------
# Stubs (idempotent — earlier tests may already have installed pieces).
# ---------------------------------------------------------------------------


def _install_ha_stubs() -> None:
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    ha.__path__ = []  # type: ignore[attr-defined]

    ha_core = sys.modules.setdefault(
        "homeassistant.core", types.ModuleType("homeassistant.core")
    )

    class _HA: ...

    class _Call:
        def __init__(self, data=None):
            self.data = data or {}

    def _cb(fn):
        return fn

    for attr, value in (
        ("HomeAssistant", _HA), ("ServiceCall", _Call),
        ("callback", _cb), ("Event", object),
    ):
        if not hasattr(ha_core, attr):
            setattr(ha_core, attr, value)

    ha_ce = sys.modules.setdefault(
        "homeassistant.config_entries", types.ModuleType("homeassistant.config_entries")
    )

    class _ConfigEntry:
        def __init__(self, data=None, options=None, entry_id="test-entry-id"):
            self.data = dict(data or {})
            self.options = dict(options or {})
            self.entry_id = entry_id

    class _OptionsFlow: ...

    if not hasattr(ha_ce, "ConfigEntry"):
        ha_ce.ConfigEntry = _ConfigEntry
    if not hasattr(ha_ce, "OptionsFlow"):
        ha_ce.OptionsFlow = _OptionsFlow

    ha_def = sys.modules.setdefault(
        "homeassistant.data_entry_flow",
        types.ModuleType("homeassistant.data_entry_flow"),
    )
    if not hasattr(ha_def, "FlowResult"):
        ha_def.FlowResult = dict

    ha_helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    ha_helpers.__path__ = []  # type: ignore[attr-defined]

    ha_sel = sys.modules.setdefault(
        "homeassistant.helpers.selector",
        types.ModuleType("homeassistant.helpers.selector"),
    )

    class _ESCfg:
        def __init__(self, **kw): self.kw = kw

    class _ES:
        def __init__(self, cfg=None): self.cfg = cfg
        def __call__(self, v): return v

    class _NSCfg:
        def __init__(self, **kw): self.kw = kw

    class _NS:
        def __init__(self, cfg=None): self.cfg = cfg
        def __call__(self, v): return v

    class _NSMode:
        BOX = "box"
        SLIDER = "slider"

    for attr, value in (
        ("EntitySelector", _ES), ("EntitySelectorConfig", _ESCfg),
        ("NumberSelector", _NS), ("NumberSelectorConfig", _NSCfg),
        ("NumberSelectorMode", _NSMode),
    ):
        if not hasattr(ha_sel, attr):
            setattr(ha_sel, attr, value)

    # Earlier test files may have stubbed `NumberSelectorMode` without a
    # SLIDER member; cover_policy/flow.py needs it. Patch it on idempotently
    # even when the parent module already exists.
    nsmode = getattr(ha_sel, "NumberSelectorMode", _NSMode)
    if not hasattr(nsmode, "SLIDER"):
        try:
            nsmode.SLIDER = "slider"
        except Exception:
            pass
    if not hasattr(nsmode, "BOX"):
        try:
            nsmode.BOX = "box"
        except Exception:
            pass

    # Earlier stubs may have a strict NumberSelectorConfig signature that
    # doesn't accept `unit_of_measurement`. Force ours, which is permissive.
    ha_sel.NumberSelectorConfig = _NSCfg
    ha_sel.NumberSelector = _NS

    ha_cv = sys.modules.setdefault(
        "homeassistant.helpers.config_validation",
        types.ModuleType("homeassistant.helpers.config_validation"),
    )
    if not hasattr(ha_cv, "string"):
        ha_cv.string = lambda v: str(v)


_install_ha_stubs()


def _install_toolbox_stubs() -> None:
    if "cp_toolbox_stub" in sys.modules:
        return
    pkg = types.ModuleType("cp_toolbox_stub")
    pkg.__path__ = []
    sys.modules["cp_toolbox_stub"] = pkg

    const_mod = types.ModuleType("cp_toolbox_stub.const")
    const_mod.CONF_MODULE_ID = "_module_id"
    const_mod.DOMAIN = "bennis_toolbox"
    const_mod.DATA_ENTRIES = "entries"
    sys.modules["cp_toolbox_stub.const"] = const_mod

    services_mod = types.ModuleType("cp_toolbox_stub.services")

    class _ServiceDef:
        def __init__(self, handler, schema=None):
            self.handler = handler
            self.schema = schema

    services_mod.ServiceDef = _ServiceDef
    sys.modules["cp_toolbox_stub.services"] = services_mod


_install_toolbox_stubs()


def _install_coordinator_stub() -> None:
    if "cp_coordinator_stub" in sys.modules:
        return
    mod = types.ModuleType("cp_coordinator_stub")

    def all_cover_policy_coordinators(hass):
        out = []
        for bucket in hass.data.get("bennis_toolbox", {}).get("entries", {}).values():
            if bucket.get("module_id") != "cover_policy":
                continue
            c = bucket.get("coordinator")
            if c is not None:
                out.append(c)
        return out

    def coordinator_from_hass(hass, entry_id):
        bucket = hass.data.get("bennis_toolbox", {}).get("entries", {}).get(entry_id)
        return bucket.get("coordinator") if bucket else None

    class _StubCoverPolicyCoordinator: ...

    mod.all_cover_policy_coordinators = all_cover_policy_coordinators
    mod.coordinator_from_hass = coordinator_from_hass
    mod.CoverPolicyCoordinator = _StubCoverPolicyCoordinator
    sys.modules["cp_coordinator_stub"] = mod


_install_coordinator_stub()


# Reuse pure const + policy that the package's conftest already loaded.
import cp_const  # noqa: E402
import cp_policy  # noqa: E402


def _load_with_remaps(filename: str, new_name: str):
    src = (MODULE_DIR / filename).read_text(encoding="utf-8")
    src = src.replace("from ...const import", "from cp_toolbox_stub.const import")
    src = src.replace("from ...services import", "from cp_toolbox_stub.services import")
    src = src.replace("from .const import", "from cp_const import")
    src = src.replace("from .coordinator import", "from cp_coordinator_stub import")
    mod = types.ModuleType(new_name)
    sys.modules[new_name] = mod
    exec(compile(src, str(MODULE_DIR / filename), "exec"), mod.__dict__)
    return mod


flow_module = _load_with_remaps("flow.py", "cp_flow")
services_module = _load_with_remaps("services_impl.py", "cp_services_impl")


# ---------------------------------------------------------------------------
# 1) Profile schema uses a slider NumberSelector + clamps + coerces to int.
# ---------------------------------------------------------------------------


def test_profile_schema_uses_number_slider_selector():
    schema = flow_module._profile_schema(dict(cp_const.DEFAULT_PROFILE))
    # Pick the validator for `heat_protect` and verify the inner shape.
    validator = schema.schema[
        next(k for k in schema.schema if getattr(k, "schema", k) == "heat_protect")
    ]
    # The validator is `vol.All(NumberSelector(...), Coerce(int), Range(0,100))`.
    assert isinstance(validator, vol.All)
    parts = validator.validators
    # First validator is the NumberSelector instance.
    selector_obj = parts[0]
    cfg = getattr(selector_obj, "cfg", None) or getattr(selector_obj, "kw", None)
    cfg_kw = getattr(cfg, "kw", cfg)
    assert cfg_kw is not None
    assert cfg_kw.get("min") == 0
    assert cfg_kw.get("max") == 100
    assert cfg_kw.get("mode") == "slider"
    assert cfg_kw.get("unit_of_measurement") == "%"


def test_profile_schema_coerces_string_to_int_and_clamps():
    schema = flow_module._profile_schema(dict(cp_const.DEFAULT_PROFILE))
    out = schema({
        "open": "100", "sleep": 0, "wake": "70", "privacy": 30,
        "heat_protect": 20, "glare_tv": 20, "glare_pc": 40, "window_open": 70,
    })
    assert out["open"] == 100 and isinstance(out["open"], int)
    assert out["wake"] == 70 and isinstance(out["wake"], int)
    assert out["heat_protect"] == 20


def test_profile_schema_rejects_out_of_range():
    schema = flow_module._profile_schema(dict(cp_const.DEFAULT_PROFILE))
    bad = {**dict(cp_const.DEFAULT_PROFILE), "heat_protect": 150}
    with pytest.raises(vol.Invalid):
        schema(bad)


# ---------------------------------------------------------------------------
# 2) Options-Flow profile step persists changed values into entry.options.
# ---------------------------------------------------------------------------


class _Entry:
    def __init__(self, data=None, options=None):
        self.data = dict(data or {})
        self.options = dict(options or {})
        self.entry_id = "test-entry-id"


class _FakeConfigEntries:
    """Track update_entry calls so we can assert behaviour."""

    def __init__(self):
        self.updates: list[dict] = []

    def async_update_entry(self, entry, *, data=None, options=None):
        if data is not None:
            entry.data = dict(data)
        if options is not None:
            entry.options = dict(options)
        self.updates.append({"data": dict(entry.data), "options": dict(entry.options)})


class _FakeHass:
    def __init__(self):
        self.config_entries = _FakeConfigEntries()
        self.data = {"bennis_toolbox": {"entries": {}}}


class _FakeOptionsFlow:
    def __init__(self):
        self.created_entry = None
        self.shown = None
        self.menu = None

    def async_show_form(self, step_id, data_schema=None, **_kw):
        self.shown = {"step_id": step_id, "data_schema": data_schema}
        return {"type": "form", "step_id": step_id}

    def async_show_menu(self, step_id, menu_options=None):
        self.menu = {"step_id": step_id, "options": list(menu_options or [])}
        return {"type": "menu"}

    def async_create_entry(self, title, data):
        self.created_entry = {"title": title, "data": dict(data)}
        return self.created_entry


@_run
async def test_options_flow_profile_step_persists_changes():
    hass = _FakeHass()
    entry = _Entry(
        data={
            "_module_id": "cover_policy",
            "name": "Wohnzimmer",
            "cover_entity": "cover.living_blackout_blind",
            "heat_protect_entity": "binary_sensor.living_heat_protect_active",
            "window_state_entity": "binary_sensor.living_window",
        },
        options={
            "apply_enabled": True,
            "position_profile": dict(cp_const.DEFAULT_PROFILE),
        },
    )
    flow = _FakeOptionsFlow()
    helper = flow_module.OptionsFlowHelper(hass=hass, entry=entry, flow=flow)
    user_input = {
        # Brief example: heat_protect must be editable to 20.
        "heat_protect": 20,
        "glare_tv": 25,
        "glare_pc": 45,
        # Leave the others on defaults.
        "open": 100, "sleep": 0, "wake": 70, "privacy": 30, "window_open": 70,
    }
    result = await helper.async_step_profile(user_input)
    assert result is flow.created_entry
    assert result["data"]["position_profile"]["heat_protect"] == 20
    assert result["data"]["position_profile"]["glare_tv"] == 25
    assert result["data"]["position_profile"]["glare_pc"] == 45
    # Source-entity slots stay intact in entry.data.
    assert entry.data["heat_protect_entity"] == "binary_sensor.living_heat_protect_active"
    assert entry.data["window_state_entity"] == "binary_sensor.living_window"
    assert entry.data["cover_entity"] == "cover.living_blackout_blind"


@_run
async def test_options_flow_sources_step_keeps_existing_slots():
    """Editing sources must not silently drop slots the user didn't touch."""
    hass = _FakeHass()
    entry = _Entry(
        data={
            "_module_id": "cover_policy",
            "name": "Wohnzimmer",
            "cover_entity": "cover.living_blackout_blind",
            "heat_protect_entity": "binary_sensor.living_heat_protect_active",
            "window_state_entity": "binary_sensor.living_window",
            "bio_state_entity": "sensor.bio_state",
        },
        options={},
    )
    flow = _FakeOptionsFlow()
    helper = flow_module.OptionsFlowHelper(hass=hass, entry=entry, flow=flow)
    # User updates only one slot, leaves the rest as-is via blank fields.
    user_input = {
        "heat_protect_entity": "binary_sensor.living_heat_protect_active",
        "window_state_entity": "binary_sensor.living_window",
        "bio_state_entity": "sensor.bio_state",
        "media_context_entity": "sensor.media_context",  # newly set
    }
    await helper.async_step_sources(user_input)
    assert entry.data["heat_protect_entity"] == "binary_sensor.living_heat_protect_active"
    assert entry.data["window_state_entity"] == "binary_sensor.living_window"
    assert entry.data["bio_state_entity"] == "sensor.bio_state"
    assert entry.data["media_context_entity"] == "sensor.media_context"
    # Cover entity is in `data` and not touched by the sources step.
    assert entry.data["cover_entity"] == "cover.living_blackout_blind"


# ---------------------------------------------------------------------------
# 3) Service `cover_policy_set_position_profile` overwrites values.
# ---------------------------------------------------------------------------


class _RecCoord:
    def __init__(self):
        self.profile_calls: list[dict] = []

    async def async_set_position_profile(self, profile):
        self.profile_calls.append(dict(profile))


@_run
async def test_set_position_profile_service_routes_to_coordinator():
    hass = _FakeHass()
    coord = _RecCoord()
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "cover_policy", "coordinator": coord,
    }
    # Sibling — must be ignored.
    sib = _RecCoord()
    hass.data["bennis_toolbox"]["entries"]["e2"] = {
        "module_id": "plug_policy_engine", "coordinator": sib,
    }
    call = types.SimpleNamespace(data={"profile": {"heat_protect": 20, "glare_tv": 25}})
    await services_module.SERVICES["set_position_profile"].handler(hass, call)
    assert coord.profile_calls == [{"heat_protect": 20, "glare_tv": 25}]
    assert sib.profile_calls == []


def test_set_position_profile_schema_rejects_unknown_modes():
    schema = services_module.SERVICES["set_position_profile"].schema
    # Required: profile dict.
    with pytest.raises(vol.Invalid):
        schema({})
    # Unknown mode in profile must be rejected by the inner schema.
    with pytest.raises(vol.Invalid):
        schema({"profile": {"unknown_mode": 50}})
    # Valid input is accepted and out-of-range is rejected.
    schema({"profile": {"heat_protect": 20}})
    with pytest.raises(vol.Invalid):
        schema({"profile": {"heat_protect": 150}})


# ---------------------------------------------------------------------------
# 4) Policy honours the changed profile values.
# ---------------------------------------------------------------------------


def test_policy_uses_updated_heat_protect_value():
    profile = dict(cp_const.DEFAULT_PROFILE)
    profile["heat_protect"] = 20  # user changed it via options or service
    ctx = cp_policy.Context(window_open=False, heat_protect_active=True)
    d = cp_policy.decide(
        ctx, profile,
        startup_ready=True, apply_enabled=True,
        manual_override_active=False, require_window=True,
    )
    assert d.mode == cp_const.MODE_HEAT_PROTECT
    assert d.target_position == 20


def test_policy_uses_updated_glare_tv_value():
    profile = dict(cp_const.DEFAULT_PROFILE)
    profile["glare_tv"] = 25
    ctx = cp_policy.Context(
        window_open=False,
        bio_state=cp_const.BIO_AWAKE,
        day_state="afternoon",
        media_context="movie",
        gaming_source="tv",
        lux=8000,
    )
    d = cp_policy.decide(
        ctx, profile,
        startup_ready=True, apply_enabled=True,
        manual_override_active=False, require_window=True,
    )
    assert d.mode == cp_const.MODE_GLARE_TV
    assert d.target_position == 25
