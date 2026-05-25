"""Smoke tests for benni_media_context's HA wiring.

These tests harden READY by exercising the config-flow helper, the entity
key contract, and the service handlers without booting a full Home
Assistant. They complement the 20 pure-logic tests in test_logic.py.
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
) / "custom_components" / "bennis_toolbox" / "modules" / "benni_media_context"


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# =========================================================================
# 1) Entity-Key contract — STATIC, no HA imports needed.
#    AST-scan entities.py and verify the 7 sensor and 4 binary-sensor _keys.
# =========================================================================


def _extract_class_keys(source: str) -> dict[str, str]:
    """Return {class_name: _key_string} for every class in source that
    assigns `_key = "..."` at class-body level.
    """
    tree = ast.parse(source)
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == "_key"
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                out[node.name] = stmt.value.value
    return out


def test_entities_expose_expected_sensor_and_binary_sensor_keys():
    src = (MODULE_DIR / "entities.py").read_text(encoding="utf-8")
    keys = _extract_class_keys(src)

    expected_sensor_keys = {
        "media_context", "media_subcontext", "media_device",
        "gaming_source", "gaming_platform",
        "volume_target_homepods", "volume_target_denon",
        "homepods_action", "audio_owner",
        "volume_policy",
    }
    expected_binary_keys = {
        "headset_active", "entertainment_active",
        "quiet_mode_active", "subwoofer_allowed",
        "homepods_should_pause", "homepods_resume_allowed",
        "volume_apply_allowed",
    }

    # Sensor classes are listed in the SENSOR branch of async_get_entities;
    # we just check that the union of _keys covers what we expect.
    all_keys = set(keys.values())
    assert expected_sensor_keys <= all_keys, (
        f"missing sensor keys: {expected_sensor_keys - all_keys}"
    )
    assert expected_binary_keys <= all_keys, (
        f"missing binary keys: {expected_binary_keys - all_keys}"
    )
    # And no other _keys snuck in.
    expected_all = expected_sensor_keys | expected_binary_keys
    assert all_keys == expected_all, f"unexpected _keys: {all_keys - expected_all}"


# =========================================================================
# 2) Config-Flow smoke — load flow.py with stubbed HA imports and exercise
#    ConfigFlowHelper against a fake umbrella flow.
# =========================================================================


def _install_ha_stubs() -> None:
    """Install minimum homeassistant stubs so flow.py + services_impl.py
    can be loaded without a real HA install."""
    if "homeassistant.helpers.selector" in sys.modules:
        return

    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    ha.__path__ = []  # type: ignore[attr-defined]

    # core
    ha_core = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))

    class _StubHomeAssistant:
        pass

    class _StubServiceCall:
        def __init__(self, data=None):
            self.data = data or {}

    def _callback(fn):
        return fn

    ha_core.HomeAssistant = _StubHomeAssistant
    ha_core.ServiceCall = _StubServiceCall
    ha_core.callback = _callback
    ha_core.Event = object

    # config_entries
    ha_ce = sys.modules.setdefault(
        "homeassistant.config_entries", types.ModuleType("homeassistant.config_entries")
    )

    class _StubConfigEntry:
        def __init__(self, data=None, options=None):
            self.data = data or {}
            self.options = options or {}
            self.entry_id = "test-entry-id"

    class _StubOptionsFlow:
        pass

    ha_ce.ConfigEntry = _StubConfigEntry
    ha_ce.OptionsFlow = _StubOptionsFlow

    # data_entry_flow
    ha_def = sys.modules.setdefault(
        "homeassistant.data_entry_flow", types.ModuleType("homeassistant.data_entry_flow")
    )
    ha_def.FlowResult = dict

    # helpers + selector + config_validation
    ha_helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    ha_helpers.__path__ = []  # type: ignore[attr-defined]

    ha_sel = sys.modules.setdefault(
        "homeassistant.helpers.selector", types.ModuleType("homeassistant.helpers.selector")
    )

    class _StubEntitySelectorConfig:
        def __init__(self, multiple=False, **_kw):
            self.multiple = multiple

    class _StubEntitySelector:
        def __init__(self, cfg=None):
            self.cfg = cfg

        # voluptuous validators must be callable.
        def __call__(self, value):
            return value

    class _StubNumberSelectorConfig:
        def __init__(self, min=None, max=None, step=None, mode=None):
            self.min, self.max, self.step, self.mode = min, max, step, mode

    class _StubNumberSelector:
        def __init__(self, cfg=None):
            self.cfg = cfg

        def __call__(self, value):
            return value

    class _NumberSelectorMode:
        BOX = "box"

    class _StubTextSelectorConfig:
        def __init__(self, type=None, **_kw):
            self.type = type

    class _StubTextSelector:
        def __init__(self, cfg=None):
            self.cfg = cfg

        def __call__(self, value):
            # voluptuous validators must be callable; plain pass-through.
            return value

    class _TextSelectorType:
        TEXT = "text"

    ha_sel.EntitySelector = _StubEntitySelector
    ha_sel.EntitySelectorConfig = _StubEntitySelectorConfig
    ha_sel.NumberSelector = _StubNumberSelector
    ha_sel.NumberSelectorConfig = _StubNumberSelectorConfig
    ha_sel.NumberSelectorMode = _NumberSelectorMode
    ha_sel.TextSelector = _StubTextSelector
    ha_sel.TextSelectorConfig = _StubTextSelectorConfig
    ha_sel.TextSelectorType = _TextSelectorType

    ha_cv = sys.modules.setdefault(
        "homeassistant.helpers.config_validation",
        types.ModuleType("homeassistant.helpers.config_validation"),
    )

    def _string(value):
        return str(value)

    ha_cv.string = _string


_install_ha_stubs()


# Provide a tiny synthetic toolbox-root package so `from ...const import
# CONF_MODULE_ID` and `from ...services import ServiceDef` resolve.
def _install_toolbox_stubs() -> None:
    if "bmc_toolbox_stub" in sys.modules:
        return

    pkg = types.ModuleType("bmc_toolbox_stub")
    pkg.__path__ = []
    sys.modules["bmc_toolbox_stub"] = pkg

    const_mod = types.ModuleType("bmc_toolbox_stub.const")
    const_mod.CONF_MODULE_ID = "_module_id"
    const_mod.DOMAIN = "bennis_toolbox"
    const_mod.DATA_ENTRIES = "entries"
    sys.modules["bmc_toolbox_stub.const"] = const_mod

    services_mod = types.ModuleType("bmc_toolbox_stub.services")

    class _ServiceDef:
        def __init__(self, handler, schema=None):
            self.handler = handler
            self.schema = schema

    services_mod.ServiceDef = _ServiceDef
    sys.modules["bmc_toolbox_stub.services"] = services_mod


_install_toolbox_stubs()


def _install_coordinator_stub() -> None:
    """services_impl.py imports lookup helpers from .coordinator. Provide a
    pure-Python stub of those that walks `hass.data` the same way."""
    if "bmc_coordinator_stub" in sys.modules:
        return

    mod = types.ModuleType("bmc_coordinator_stub")

    def all_benni_media_context_coordinators(hass):
        out = []
        for bucket in hass.data.get("bennis_toolbox", {}).get("entries", {}).values():
            if bucket.get("module_id") != "benni_media_context":
                continue
            c = bucket.get("coordinator")
            if c is not None:
                out.append(c)
        return out

    mod.all_benni_media_context_coordinators = all_benni_media_context_coordinators

    class _StubBenniMediaCoordinator:
        pass

    mod.BenniMediaCoordinator = _StubBenniMediaCoordinator

    def coordinator_from_hass(hass, entry_id):
        bucket = hass.data.get("bennis_toolbox", {}).get("entries", {}).get(entry_id)
        return bucket.get("coordinator") if bucket else None

    mod.coordinator_from_hass = coordinator_from_hass
    sys.modules["bmc_coordinator_stub"] = mod


_install_coordinator_stub()


def _load_module_source_with_remapped_parents(filename: str, new_name: str):
    """Load a module source file with its `from ...<x>` imports rewritten
    to point at the synthetic `bmc_toolbox_stub` package, and `from .const`
    to the already-loaded bmc_const.
    """
    src = (MODULE_DIR / filename).read_text(encoding="utf-8")
    src = src.replace("from ...const import", "from bmc_toolbox_stub.const import")
    src = src.replace("from ...services import", "from bmc_toolbox_stub.services import")
    src = src.replace("from .const import", "from bmc_const import")
    src = src.replace("from .coordinator import", "from bmc_coordinator_stub import")
    mod = types.ModuleType(new_name)
    sys.modules[new_name] = mod
    exec(compile(src, str(MODULE_DIR / filename), "exec"), mod.__dict__)
    return mod


flow_module = _load_module_source_with_remapped_parents("flow.py", "bmc_flow")
services_module = _load_module_source_with_remapped_parents(
    "services_impl.py", "bmc_services_impl"
)


class _AbortFlowError(Exception):
    """Stand-in for HomeAssistant's AbortFlow."""


class _FakeUmbrellaFlow:
    """Records form/entry calls and mimics the umbrella ConfigFlow API."""

    def __init__(self, already_configured: bool = False):
        self.already_configured = already_configured
        self.unique_id: str | None = None
        self.last_form: dict | None = None
        self.created_entry: dict | None = None

    async def async_set_unique_id(self, value: str):
        self.unique_id = value

    def _abort_if_unique_id_configured(self):
        if self.already_configured:
            raise _AbortFlowError("already configured")

    def async_show_form(self, step_id, data_schema=None, **_kw):
        self.last_form = {
            "step_id": step_id,
            "data_schema": data_schema,
        }
        return {"type": "form", "step_id": step_id}

    def async_create_entry(self, title, data, options=None):
        self.created_entry = {
            "type": "create_entry",
            "title": title,
            "data": dict(data),
            "options": dict(options or {}),
        }
        return self.created_entry


@_run
async def test_config_flow_first_step_sets_singleton_and_shows_form():
    flow = _FakeUmbrellaFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    result = await helper.async_step_init()

    assert flow.unique_id == "benni_media_context_singleton"
    assert result["step_id"] == "module_step"
    assert flow.last_form is not None


@_run
async def test_config_flow_aborts_when_singleton_already_configured():
    flow = _FakeUmbrellaFlow(already_configured=True)
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    with pytest.raises(_AbortFlowError):
        await helper.async_step_init()


@_run
async def test_config_flow_creates_entry_with_module_id():
    flow = _FakeUmbrellaFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    await helper.async_step_init()
    # Empty user input is allowed — every source slot is optional.
    result = await helper.async_step_module_step({})
    assert result["type"] == "create_entry"
    assert result["title"] == "Benni Media Context"
    assert result["data"]["_module_id"] == "benni_media_context"


@_run
async def test_config_flow_drops_empty_entity_slots():
    flow = _FakeUmbrellaFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    await helper.async_step_init()
    user_input = {
        "tv_active": "binary_sensor.tv_on",
        "ps5_status": "",         # explicit empty
        "homepods": [],            # empty list
        "classifier_media": "sensor.title_classifier_media_enum",
    }
    result = await helper.async_step_module_step(user_input)
    data = result["data"]
    assert data["_module_id"] == "benni_media_context"
    assert data["tv_active"] == "binary_sensor.tv_on"
    assert data["classifier_media"] == "sensor.title_classifier_media_enum"
    assert "ps5_status" not in data
    assert "homepods" not in data


# =========================================================================
# 3) Service smoke — verify SERVICES dict shape AND that start_radio /
#    stop_media fire the toolbox-prefixed events with the right payload.
# =========================================================================


def test_services_have_the_five_expected_actions():
    assert set(services_module.SERVICES.keys()) == {
        "force_recalculate", "set_manual_nudge", "clear_manual_nudge",
        "start_radio", "stop_media",
    }


def test_set_manual_nudge_schema_requires_subcontext():
    schema = services_module.SERVICES["set_manual_nudge"].schema
    assert schema is not None
    with pytest.raises(vol.Invalid):
        schema({})
    assert schema({"subcontext": "streaming_netflix"})["subcontext"] == "streaming_netflix"


class _FakeBus:
    def __init__(self):
        self.fired: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, event_data: dict | None = None):
        self.fired.append((event_type, event_data or {}))


class _FakeHassWithBus:
    def __init__(self):
        self.bus = _FakeBus()
        # Empty data buckets so coordinator-lookup helpers don't choke
        # when force_recalculate / nudge handlers iterate.
        self.data = {"bennis_toolbox": {"entries": {}}}


class _FakeServiceCall:
    def __init__(self, data=None):
        self.data = data or {}


@_run
async def test_start_radio_fires_toolbox_prefixed_event():
    hass = _FakeHassWithBus()
    call = _FakeServiceCall({"station": "Radio Bob"})
    await services_module.SERVICES["start_radio"].handler(hass, call)
    assert hass.bus.fired == [
        ("bennis_toolbox_benni_media_context_start_radio", {"station": "Radio Bob"}),
    ]


@_run
async def test_stop_media_fires_toolbox_prefixed_event():
    hass = _FakeHassWithBus()
    call = _FakeServiceCall({})
    await services_module.SERVICES["stop_media"].handler(hass, call)
    assert hass.bus.fired == [
        ("bennis_toolbox_benni_media_context_stop_media", {}),
    ]


@_run
async def test_force_recalculate_iterates_loaded_coordinators():
    """With no loaded coordinators, the handler must be a safe no-op
    rather than crashing on an empty dict."""
    hass = _FakeHassWithBus()
    await services_module.SERVICES["force_recalculate"].handler(hass, _FakeServiceCall())
    # No event, no exception — that's the contract.
    assert hass.bus.fired == []


class _RecordingCoordinator:
    def __init__(self):
        self.recalc_calls = 0
        self.nudge_calls: list[str | None] = []

    async def async_recalculate(self):
        self.recalc_calls += 1

    def set_manual_nudge(self, value: str):
        self.nudge_calls.append(value)

    def clear_manual_nudge(self):
        self.nudge_calls.append(None)


@_run
async def test_set_and_clear_manual_nudge_reach_coordinators():
    hass = _FakeHassWithBus()
    coord = _RecordingCoordinator()
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "benni_media_context", "coordinator": coord,
    }
    # Inject a sibling module to confirm the lookup filters by module_id.
    hass.data["bennis_toolbox"]["entries"]["e2"] = {
        "module_id": "wake_planner", "coordinator": _RecordingCoordinator(),
    }
    await services_module.SERVICES["set_manual_nudge"].handler(
        hass, _FakeServiceCall({"subcontext": "streaming_disney"})
    )
    await services_module.SERVICES["clear_manual_nudge"].handler(
        hass, _FakeServiceCall()
    )
    assert coord.nudge_calls == ["streaming_disney", None]
    # The wake_planner coordinator must have been ignored.
    other = hass.data["bennis_toolbox"]["entries"]["e2"]["coordinator"]
    assert other.nudge_calls == []


@_run
async def test_force_recalculate_calls_only_benni_media_context_coordinators():
    hass = _FakeHassWithBus()
    mine = _RecordingCoordinator()
    foreign = _RecordingCoordinator()
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "benni_media_context", "coordinator": mine,
    }
    hass.data["bennis_toolbox"]["entries"]["e2"] = {
        "module_id": "wake_planner", "coordinator": foreign,
    }
    await services_module.SERVICES["force_recalculate"].handler(hass, _FakeServiceCall())
    assert mine.recalc_calls == 1
    assert foreign.recalc_calls == 0
