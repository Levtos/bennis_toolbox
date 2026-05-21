"""Config/service/entity smoke tests for cover_policy."""
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


def _install_ha_stubs() -> None:
    if "homeassistant.helpers.selector" in sys.modules:
        return

    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    ha.__path__ = []  # type: ignore[attr-defined]

    ha_core = sys.modules.setdefault(
        "homeassistant.core", types.ModuleType("homeassistant.core")
    )

    class _HA: ...

    class _Call:
        def __init__(self, data=None):
            self.data = data or {}

    ha_core.HomeAssistant = _HA
    ha_core.ServiceCall = _Call

    ha_ce = sys.modules.setdefault(
        "homeassistant.config_entries", types.ModuleType("homeassistant.config_entries")
    )

    class _ConfigEntry:
        def __init__(self, data=None, options=None):
            self.data = data or {}
            self.options = options or {}
            self.entry_id = "test-entry-id"

    class _OptionsFlow: ...

    ha_ce.ConfigEntry = _ConfigEntry
    ha_ce.OptionsFlow = _OptionsFlow

    ha_def = sys.modules.setdefault(
        "homeassistant.data_entry_flow", types.ModuleType("homeassistant.data_entry_flow")
    )
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
        def __init__(self, **kw):
            self.kw = kw

    class _ES:
        def __init__(self, cfg=None):
            self.cfg = cfg
        def __call__(self, v):
            return v

    ha_sel.EntitySelector = _ES
    ha_sel.EntitySelectorConfig = _ESCfg

    ha_cv = sys.modules.setdefault(
        "homeassistant.helpers.config_validation",
        types.ModuleType("homeassistant.helpers.config_validation"),
    )
    ha_cv.string = lambda v: str(v)


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

    mod.all_cover_policy_coordinators = all_cover_policy_coordinators
    mod.coordinator_from_hass = coordinator_from_hass
    sys.modules["cp_coordinator_stub"] = mod


_install_ha_stubs()
_install_toolbox_stubs()
_install_coordinator_stub()

import cp_const as C  # noqa: E402


def _load_with_remap(filename: str, new_name: str):
    src = (MODULE_DIR / filename).read_text(encoding="utf-8")
    src = src.replace("from ...const import", "from cp_toolbox_stub.const import")
    src = src.replace("from ...services import", "from cp_toolbox_stub.services import")
    src = src.replace("from .const import", "from cp_const import")
    src = src.replace("from .coordinator import", "from cp_coordinator_stub import")
    mod = types.ModuleType(new_name)
    sys.modules[new_name] = mod
    exec(compile(src, str(MODULE_DIR / filename), "exec"), mod.__dict__)
    return mod


flow_module = _load_with_remap("flow.py", "cp_flow")
services_module = _load_with_remap("services_impl.py", "cp_services_impl")


def _extract_unique_suffixes(source: str) -> set[str]:
    tree = ast.parse(source)
    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "const"
        ):
            # Relative import; values are resolved from cp_const below.
            for alias in node.names:
                v = getattr(C, alias.name, None)
                if isinstance(v, str):
                    constants[alias.asname or alias.name] = v
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "unique_id":
            args = node.args
            if not args:
                continue
            last = args[-1]
            if isinstance(last, ast.Constant) and isinstance(last.value, str):
                out.add(last.value)
            elif isinstance(last, ast.Name) and last.id in constants:
                out.add(constants[last.id])
    return out


def test_entities_expose_expected_unique_id_suffixes():
    src = (MODULE_DIR / "entities.py").read_text(encoding="utf-8")
    assert _extract_unique_suffixes(src) == {
        C.UID_MODE,
        C.UID_TARGET,
        C.UID_REASON,
        C.UID_APPLY_BLOCKED,
        C.UID_DEBUG,
    }


class _AbortFlowError(Exception): ...


class _FakeFlow:
    def __init__(self, already_configured=False):
        self.already_configured = already_configured
        self.unique_id = None
        self.last_form = None

    async def async_set_unique_id(self, value):
        self.unique_id = value

    def _abort_if_unique_id_configured(self):
        if self.already_configured:
            raise _AbortFlowError("already configured")

    def async_show_form(self, step_id, data_schema=None, errors=None, **_kw):
        self.last_form = {"step_id": step_id, "data_schema": data_schema, "errors": errors or {}}
        return {"type": "form", "step_id": step_id, "errors": errors or {}}

    def async_create_entry(self, title, data, options=None):
        return {"type": "create_entry", "title": title, "data": dict(data), "options": dict(options or {})}


@_run
async def test_config_flow_init_shows_module_step():
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=_FakeFlow())
    result = await helper.async_step_init()
    assert result["type"] == "form"
    assert result["step_id"] == "module_step"


@_run
async def test_config_flow_rejects_missing_cover_entity():
    flow = _FakeFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    result = await helper.async_step_module_step({C.CONF_NAME: "Living"})
    assert result["errors"][C.CONF_COVER_ENTITY] == "required"


@_run
async def test_config_flow_creates_entry_with_module_id_defaults_and_profile():
    flow = _FakeFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    result = await helper.async_step_module_step({
        C.CONF_NAME: "Living Blind",
        C.CONF_COVER_ENTITY: "cover.living_blackout_blind",
        C.CONF_WINDOW_STATE: "binary_sensor.living_window_open",
        C.CONF_APPLY_ENABLED: False,
    })
    assert flow.unique_id == "cover_policy:cover.living_blackout_blind"
    assert result["type"] == "create_entry"
    assert result["data"]["_module_id"] == "cover_policy"
    assert result["data"][C.CONF_COVER_ENTITY] == "cover.living_blackout_blind"
    assert result["data"][C.CONF_WINDOW_STATE] == "binary_sensor.living_window_open"
    assert result["options"][C.CONF_APPLY_ENABLED] is False
    assert result["options"][C.CONF_PROFILE] == C.DEFAULT_PROFILE


@_run
async def test_config_flow_aborts_duplicate_cover():
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=_FakeFlow(already_configured=True))
    with pytest.raises(_AbortFlowError):
        await helper.async_step_module_step({
            C.CONF_NAME: "Living Blind",
            C.CONF_COVER_ENTITY: "cover.living_blackout_blind",
        })


def test_services_have_expected_actions_and_schemas():
    assert set(services_module.SERVICES) == {
        C.SERVICE_APPLY_NOW,
        C.SERVICE_SET_MANUAL_OVERRIDE,
        C.SERVICE_CLEAR_MANUAL_OVERRIDE,
        C.SERVICE_SET_POSITION_PROFILE,
    }
    profile_schema = services_module.SERVICES[C.SERVICE_SET_POSITION_PROFILE].schema
    assert profile_schema({"profile": {C.MODE_SLEEP: 42}})["profile"][C.MODE_SLEEP] == 42
    with pytest.raises(vol.Invalid):
        profile_schema({"profile": {C.MODE_SLEEP: 101}})


class _RecordingCoordinator:
    def __init__(self):
        self.apply_calls = 0
        self.override_calls: list[int | None] = []
        self.clear_calls = 0
        self.profile_calls: list[dict] = []

    async def async_apply_now(self):
        self.apply_calls += 1

    async def async_set_manual_override(self, duration=None):
        self.override_calls.append(duration)

    async def async_clear_manual_override(self):
        self.clear_calls += 1

    async def async_set_position_profile(self, profile):
        self.profile_calls.append(dict(profile))


class _FakeHass:
    def __init__(self):
        self.data = {"bennis_toolbox": {"entries": {}}}


class _FakeCall:
    def __init__(self, data=None):
        self.data = data or {}


@_run
async def test_service_fanout_only_targets_cover_policy_coordinators():
    hass = _FakeHass()
    mine = _RecordingCoordinator()
    other = _RecordingCoordinator()
    hass.data["bennis_toolbox"]["entries"]["cover"] = {
        "module_id": "cover_policy",
        "coordinator": mine,
    }
    hass.data["bennis_toolbox"]["entries"]["plug"] = {
        "module_id": "plug_policy_engine",
        "coordinator": other,
    }
    await services_module.SERVICES[C.SERVICE_APPLY_NOW].handler(hass, _FakeCall())
    assert mine.apply_calls == 1
    assert other.apply_calls == 0


@_run
async def test_services_route_entry_id_override_clear_and_profile():
    hass = _FakeHass()
    coord = _RecordingCoordinator()
    hass.data["bennis_toolbox"]["entries"]["entry-a"] = {
        "module_id": "cover_policy",
        "coordinator": coord,
    }
    await services_module.SERVICES[C.SERVICE_SET_MANUAL_OVERRIDE].handler(
        hass, _FakeCall({"entry_id": "entry-a", "duration": 123})
    )
    await services_module.SERVICES[C.SERVICE_CLEAR_MANUAL_OVERRIDE].handler(
        hass, _FakeCall({"entry_id": "entry-a"})
    )
    await services_module.SERVICES[C.SERVICE_SET_POSITION_PROFILE].handler(
        hass, _FakeCall({"entry_id": "entry-a", "profile": {C.MODE_SLEEP: 12}})
    )
    assert coord.override_calls == [123]
    assert coord.clear_calls == 1
    assert coord.profile_calls == [{C.MODE_SLEEP: 12}]
