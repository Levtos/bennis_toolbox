"""Config/service/entity smoke tests for plug_policy_engine, mirroring
the benni_media_context pattern."""

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
) / "custom_components" / "bennis_toolbox" / "modules" / "plug_policy_engine"


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# =========================================================================
# 1) HA + toolbox stubs (shared layout with benni_media_context smoke).
# =========================================================================


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

    def _cb(fn):
        return fn

    ha_core.HomeAssistant = _HA
    ha_core.ServiceCall = _Call
    ha_core.callback = _cb
    ha_core.Event = object

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
        def __init__(self, cfg=None): self.cfg = cfg
        def __call__(self, v): return v

    class _SSCfg:
        def __init__(self, **kw):
            self.kw = kw

    class _SS:
        def __init__(self, cfg=None): self.cfg = cfg
        def __call__(self, v): return v

    class _SSMode:
        LIST = "list"

    ha_sel.EntitySelector = _ES
    ha_sel.EntitySelectorConfig = _ESCfg
    ha_sel.SelectSelector = _SS
    ha_sel.SelectSelectorConfig = _SSCfg
    ha_sel.SelectSelectorMode = _SSMode

    ha_cv = sys.modules.setdefault(
        "homeassistant.helpers.config_validation",
        types.ModuleType("homeassistant.helpers.config_validation"),
    )
    ha_cv.string = lambda v: str(v)


_install_ha_stubs()


def _install_toolbox_stubs() -> None:
    if "pp_toolbox_stub" in sys.modules:
        return
    pkg = types.ModuleType("pp_toolbox_stub")
    pkg.__path__ = []
    sys.modules["pp_toolbox_stub"] = pkg

    const_mod = types.ModuleType("pp_toolbox_stub.const")
    const_mod.CONF_MODULE_ID = "_module_id"
    const_mod.DOMAIN = "bennis_toolbox"
    const_mod.DATA_ENTRIES = "entries"
    sys.modules["pp_toolbox_stub.const"] = const_mod

    services_mod = types.ModuleType("pp_toolbox_stub.services")

    class _ServiceDef:
        def __init__(self, handler, schema=None):
            self.handler = handler
            self.schema = schema

    services_mod.ServiceDef = _ServiceDef
    sys.modules["pp_toolbox_stub.services"] = services_mod


_install_toolbox_stubs()


def _install_coordinator_stub() -> None:
    if "pp_coordinator_stub" in sys.modules:
        return
    mod = types.ModuleType("pp_coordinator_stub")

    def all_plug_policy_coordinators(hass):
        out = []
        for bucket in hass.data.get("bennis_toolbox", {}).get("entries", {}).values():
            if bucket.get("module_id") != "plug_policy_engine":
                continue
            c = bucket.get("coordinator")
            if c is not None:
                out.append(c)
        return out

    def coordinator_for_device(hass, device_id):
        for c in all_plug_policy_coordinators(hass):
            if device_id in c.configs:
                return c
        return None

    def coordinator_from_hass(hass, entry_id):
        bucket = hass.data.get("bennis_toolbox", {}).get("entries", {}).get(entry_id)
        return bucket.get("coordinator") if bucket else None

    class _StubPlugPolicyCoordinator: ...

    mod.all_plug_policy_coordinators = all_plug_policy_coordinators
    mod.coordinator_for_device = coordinator_for_device
    mod.coordinator_from_hass = coordinator_from_hass
    mod.PlugPolicyCoordinator = _StubPlugPolicyCoordinator
    sys.modules["pp_coordinator_stub"] = mod


_install_coordinator_stub()


# Reuse the local pure const module that conftest.py already loaded.
import pp_const  # noqa: E402


def _load_module_source(filename: str, new_name: str):
    src = (MODULE_DIR / filename).read_text(encoding="utf-8")
    src = src.replace("from ...const import", "from pp_toolbox_stub.const import")
    src = src.replace("from ...services import", "from pp_toolbox_stub.services import")
    src = src.replace("from .const import", "import pp_const as _pc; ")
    # The naive substitution above produces `from .const import X, Y` which
    # we still need to rewrite. Do it more carefully:
    return _load_with_const_remap(filename, new_name)


def _load_with_const_remap(filename: str, new_name: str):
    src = (MODULE_DIR / filename).read_text(encoding="utf-8")
    src = src.replace("from ...const import", "from pp_toolbox_stub.const import")
    src = src.replace("from ...services import", "from pp_toolbox_stub.services import")
    src = src.replace("from .const import", "from pp_const import")
    src = src.replace("from .coordinator import", "from pp_coordinator_stub import")
    mod = types.ModuleType(new_name)
    sys.modules[new_name] = mod
    exec(compile(src, str(MODULE_DIR / filename), "exec"), mod.__dict__)
    return mod


flow_module = _load_with_const_remap("flow.py", "pp_flow")
services_module = _load_with_const_remap("services_impl.py", "pp_services_impl")


# =========================================================================
# 2) Entity-Key contract via AST scan.
# =========================================================================


def _extract_unique_id_suffixes(source: str) -> set[str]:
    """Find literal entity suffixes used for hub and per-device unique IDs."""
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "unique_id":
            args = node.args
            if args and isinstance(args[-1], ast.Constant) and isinstance(args[-1].value, str):
                out.add(args[-1].value)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "__init__"
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Name)
            and node.func.value.func.id == "super"
        ):
            args = node.args
            if args and isinstance(args[-1], ast.Constant) and isinstance(args[-1].value, str):
                out.add(args[-1].value)
    return out


def test_entities_expose_expected_unique_id_suffixes():
    src = (MODULE_DIR / "entities.py").read_text(encoding="utf-8")
    suffixes = _extract_unique_id_suffixes(src)
    # Hub-level: summary, any_blocked. Per-device: policy_state, decision,
    # last_action, active.
    expected = {"summary", "any_blocked", "policy_state", "decision", "last_action", "active"}
    assert suffixes == expected, suffixes


# =========================================================================
# 3) Config-flow smoke.
# =========================================================================


class _AbortFlowError(Exception): ...


class _FakeFlow:
    def __init__(self, already_configured=False):
        self.already_configured = already_configured
        self.unique_id = None
        self.last_form = None
        self.created_entry = None
        self.last_menu = None

    async def async_set_unique_id(self, v):
        self.unique_id = v

    def _abort_if_unique_id_configured(self):
        if self.already_configured:
            raise _AbortFlowError("already configured")

    def async_show_form(self, step_id, data_schema=None, **_kw):
        self.last_form = {"step_id": step_id, "data_schema": data_schema}
        return {"type": "form", "step_id": step_id}

    def async_show_menu(self, step_id, menu_options=None):
        self.last_menu = {"step_id": step_id, "menu_options": list(menu_options or [])}
        return {"type": "menu", "step_id": step_id}

    def async_create_entry(self, title, data, options=None):
        self.created_entry = {
            "type": "create_entry",
            "title": title, "data": dict(data),
            "options": dict(options or {}),
        }
        return self.created_entry

    def async_abort(self, reason):
        return {"type": "abort", "reason": reason}


@_run
async def test_config_flow_init_sets_singleton_and_shows_form():
    flow = _FakeFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    result = await helper.async_step_init()
    assert flow.unique_id == "plug_policy_engine_singleton"
    assert result["step_id"] == "module_step"


@_run
async def test_config_flow_aborts_second_instance():
    flow = _FakeFlow(already_configured=True)
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    with pytest.raises(_AbortFlowError):
        await helper.async_step_init()


@_run
async def test_config_flow_creates_entry_with_module_id_and_empty_devices():
    flow = _FakeFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    await helper.async_step_init()
    result = await helper.async_step_module_step({"enable_control": True, "scan_interval": 60})
    assert result["type"] == "create_entry"
    assert result["data"]["_module_id"] == "plug_policy_engine"
    # devices list starts empty — devices are added later via the options flow.
    assert result["data"]["devices"] == []
    assert result["data"]["enable_control"] is True
    assert result["data"]["scan_interval"] == 60


# =========================================================================
# 4) Service-Smoke.
# =========================================================================


def test_services_have_the_five_expected_actions():
    assert set(services_module.SERVICES.keys()) == {
        "force_evaluate", "apply_policy_now",
        "suspend_device_policy", "resume_device_policy",
        "set_manual_recently_on",
    }


def test_suspend_schema_requires_device_id():
    schema = services_module.SERVICES["suspend_device_policy"].schema
    assert schema is not None
    with pytest.raises(vol.Invalid):
        schema({})
    assert schema({"device_id": "dev1"})["device_id"] == "dev1"


class _RecordingCoordinator:
    def __init__(self, configs=None):
        self.configs = configs or {}
        self.evaluate_calls = 0
        self.apply_now_calls: list[str | None] = []
        self.suspend_calls: list[tuple[str, bool]] = []
        self.manual_calls: list[str] = []

    async def async_evaluate_all(self):
        self.evaluate_calls += 1

    async def async_apply_now(self, device_id=None):
        self.apply_now_calls.append(device_id)

    async def async_suspend(self, device_id, suspend):
        self.suspend_calls.append((device_id, suspend))

    async def async_mark_manual_on(self, device_id):
        self.manual_calls.append(device_id)


class _FakeHass:
    def __init__(self):
        self.data = {"bennis_toolbox": {"entries": {}}}


class _FakeCall:
    def __init__(self, data=None):
        self.data = data or {}


@_run
async def test_force_evaluate_iterates_only_plug_policy_engine_coordinators():
    hass = _FakeHass()
    mine = _RecordingCoordinator()
    other = _RecordingCoordinator()
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "plug_policy_engine", "coordinator": mine,
    }
    hass.data["bennis_toolbox"]["entries"]["e2"] = {
        "module_id": "wake_planner", "coordinator": other,
    }
    await services_module.SERVICES["force_evaluate"].handler(hass, _FakeCall())
    assert mine.evaluate_calls == 1
    assert other.evaluate_calls == 0


@_run
async def test_suspend_and_resume_route_by_device_id():
    hass = _FakeHass()
    coord = _RecordingCoordinator(configs={"plug_a": object(), "plug_b": object()})
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "plug_policy_engine", "coordinator": coord,
    }
    await services_module.SERVICES["suspend_device_policy"].handler(
        hass, _FakeCall({"device_id": "plug_b"})
    )
    await services_module.SERVICES["resume_device_policy"].handler(
        hass, _FakeCall({"device_id": "plug_b"})
    )
    assert coord.suspend_calls == [("plug_b", True), ("plug_b", False)]


@_run
async def test_suspend_unknown_device_is_safe_no_op():
    hass = _FakeHass()
    await services_module.SERVICES["suspend_device_policy"].handler(
        hass, _FakeCall({"device_id": "ghost"})
    )
    # No coordinators, no crash.


@_run
async def test_apply_now_with_no_device_iterates_all():
    hass = _FakeHass()
    coord = _RecordingCoordinator(configs={"plug_a": object()})
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "plug_policy_engine", "coordinator": coord,
    }
    await services_module.SERVICES["apply_policy_now"].handler(hass, _FakeCall())
    assert coord.apply_now_calls == [None]


@_run
async def test_apply_now_with_device_targets_that_coordinator():
    hass = _FakeHass()
    coord = _RecordingCoordinator(configs={"plug_a": object()})
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "plug_policy_engine", "coordinator": coord,
    }
    await services_module.SERVICES["apply_policy_now"].handler(
        hass, _FakeCall({"device_id": "plug_a"})
    )
    assert coord.apply_now_calls == ["plug_a"]


@_run
async def test_mark_manual_recently_on_routes_correctly():
    hass = _FakeHass()
    coord = _RecordingCoordinator(configs={"plug_pc": object()})
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "plug_policy_engine", "coordinator": coord,
    }
    await services_module.SERVICES["set_manual_recently_on"].handler(
        hass, _FakeCall({"device_id": "plug_pc"})
    )
    assert coord.manual_calls == ["plug_pc"]
