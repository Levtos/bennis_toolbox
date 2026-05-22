"""Smoke tests for the umbrella OptionsFlow used by cover_policy.

Regression target: HA 2024.12+ raised "500 Internal Server Error" when the
gear icon was clicked because `BennisToolboxOptionsFlow.__init__` assigned
to `self.config_entry`, which is a managed property on modern HA. The fix
is to instantiate the OptionsFlow without arguments and let the framework
wire `config_entry` itself.

These tests load the umbrella's `config_flow.py` standalone with minimal
HA stubs that emulate the modern behaviour (config_entry as a managed
property).
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from functools import wraps
from pathlib import Path

import pytest


ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
UMBRELLA_DIR = ROOT / "custom_components" / "bennis_toolbox"


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# ---------------------------------------------------------------------------
# Minimal HA stubs that model the *modern* OptionsFlow contract.
# ---------------------------------------------------------------------------


def _install_ha_stubs() -> None:
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    ha.__path__ = []  # type: ignore[attr-defined]

    ha_core = sys.modules.setdefault(
        "homeassistant.core", types.ModuleType("homeassistant.core")
    )

    def _cb(fn):
        return fn

    class _HA:
        def __init__(self):
            self.data = {}

        async def async_add_executor_job(self, fn, *args):
            return fn(*args)

    # Force-replace: earlier sibling stubs install a barebones HomeAssistant
    # without `async_add_executor_job`, which the umbrella OptionsFlow needs.
    ha_core.HomeAssistant = _HA
    if not hasattr(ha_core, "callback"):
        ha_core.callback = _cb

    ha_ce = sys.modules.setdefault(
        "homeassistant.config_entries", types.ModuleType("homeassistant.config_entries")
    )

    class _ConfigEntry:
        def __init__(self, data=None, options=None, entry_id="e1"):
            self.data = dict(data or {})
            self.options = dict(options or {})
            self.entry_id = entry_id

    class _ConfigFlow:
        # Domain-keyword swallow on subclass, like real HA.
        def __init_subclass__(cls, domain=None, **kw):  # noqa: D401
            super().__init_subclass__(**kw)
            cls._domain = domain

        def __init__(self):
            self.hass = None

        def async_show_form(self, **kw):
            return {"type": "form", **kw}

        def async_create_entry(self, **kw):
            return {"type": "create_entry", **kw}

        def async_abort(self, **kw):
            return {"type": "abort", **kw}

    class _OptionsFlow:
        """Models HA 2024.12+: `config_entry` is a managed property.

        Assigning to it from a subclass `__init__` raises AttributeError,
        which is exactly the "500 Internal Server Error" symptom we're
        regression-testing for.
        """

        _bound_entry = None  # set by the framework before steps run.

        @property
        def config_entry(self):  # noqa: D401
            return self._bound_entry

        # No setter — assignment must fail.

        def async_show_form(self, **kw):
            return {"type": "form", **kw}

        def async_show_menu(self, **kw):
            return {"type": "menu", **kw}

        def async_create_entry(self, **kw):
            return {"type": "create_entry", **kw}

        def async_abort(self, **kw):
            return {"type": "abort", **kw}

    if not hasattr(ha_ce, "ConfigEntry"):
        ha_ce.ConfigEntry = _ConfigEntry
    # Always replace these — earlier sibling stubs use permissive
    # placeholders that don't model the property-getter contract.
    ha_ce.ConfigFlow = _ConfigFlow
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

    class _Sel:
        def __init__(self, *a, **kw): pass
        def __call__(self, v): return v

    class _Cfg:
        def __init__(self, *a, **kw): pass

    class _SelMode:
        LIST = "list"
        DROPDOWN = "dropdown"

    for attr, value in (
        ("SelectSelector", _Sel),
        ("SelectSelectorConfig", _Cfg),
        ("SelectSelectorMode", _SelMode),
        ("SelectOptionDict", dict),
    ):
        if not hasattr(ha_sel, attr):
            setattr(ha_sel, attr, value)
    # Earlier-installed stubs may lack new members the sibling tests need.
    mode_cls = getattr(ha_sel, "SelectSelectorMode", _SelMode)
    for member, val in (("LIST", "list"), ("DROPDOWN", "dropdown")):
        if not hasattr(mode_cls, member):
            try:
                setattr(mode_cls, member, val)
            except Exception:
                pass


_install_ha_stubs()


# ---------------------------------------------------------------------------
# Load the umbrella `config_flow.py` as a synthetic package so its relative
# imports (`.const`, `.modules`, `.modules.base`) all resolve.
# ---------------------------------------------------------------------------


def _load_umbrella() -> types.ModuleType:
    if "ofs_umbrella" in sys.modules:
        return sys.modules["ofs_umbrella"]

    pkg = types.ModuleType("ofs_umbrella")
    pkg.__path__ = [str(UMBRELLA_DIR)]
    sys.modules["ofs_umbrella"] = pkg

    # const
    const_src = (UMBRELLA_DIR / "const.py").read_text(encoding="utf-8")
    const_mod = types.ModuleType("ofs_umbrella.const")
    sys.modules["ofs_umbrella.const"] = const_mod
    exec(compile(const_src, str(UMBRELLA_DIR / "const.py"), "exec"), const_mod.__dict__)

    # modules package stub — emulates the minimal API config_flow needs.
    modules_pkg = types.ModuleType("ofs_umbrella.modules")
    modules_pkg.__path__ = []
    sys.modules["ofs_umbrella.modules"] = modules_pkg

    class _ModuleStatus:
        PENDING = type("S", (), {"value": "pending"})()
        STUB = type("S", (), {"value": "stub"})()
        READY = type("S", (), {"value": "ready"})()

    base_mod = types.ModuleType("ofs_umbrella.modules.base")
    base_mod.ModuleStatus = _ModuleStatus
    sys.modules["ofs_umbrella.modules.base"] = base_mod

    class _Spec:
        def __init__(self, module_id, name):
            self.module_id = module_id
            self.name = name
            self.status = _ModuleStatus.READY

    _SPEC = _Spec("cover_policy", "Cover Policy")
    modules_pkg.REGISTERED_MODULE_IDS = {"cover_policy"}
    modules_pkg.get_spec = lambda mid: _SPEC
    modules_pkg.selectable_specs = lambda: [_SPEC]

    # `load_module` returns an object with OptionsFlowHelper; we record
    # whether the helper was constructed so tests can assert delegation.
    class _StubHelper:
        def __init__(self, hass, entry, flow):
            self.hass = hass
            self.entry = entry
            self.flow = flow
            # The helper is allowed to read flow.config_entry — that's
            # exactly what the production cover_policy helper does. Touch
            # it here so the test catches any regression.
            _ = flow.config_entry

        async def async_step_init(self, user_input=None):
            return {
                "type": "menu",
                "step_id": "init",
                "menu_options": ["sources", "profile", "runtime"],
            }

        async def async_step_sources(self, user_input=None):
            return {"type": "form", "step_id": "sources", "user_input": user_input}

        async def async_step_runtime(self, user_input=None):
            return {"type": "form", "step_id": "runtime", "user_input": user_input}

    class _StubModule:
        OptionsFlowHelper = _StubHelper

    modules_pkg.load_module = lambda mid: _StubModule

    # Finally, load config_flow itself.
    src = (UMBRELLA_DIR / "config_flow.py").read_text(encoding="utf-8")
    # Rewrite relative imports to point at our synthetic package.
    src = src.replace("from .const import", "from ofs_umbrella.const import")
    src = src.replace("from .modules import", "from ofs_umbrella.modules import")
    src = src.replace("from .modules.base import", "from ofs_umbrella.modules.base import")
    mod = types.ModuleType("ofs_umbrella.config_flow")
    sys.modules["ofs_umbrella.config_flow"] = mod
    exec(compile(src, str(UMBRELLA_DIR / "config_flow.py"), "exec"), mod.__dict__)
    return mod


umbrella = _load_umbrella()


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


def test_async_get_options_flow_does_not_explode():
    """Regression for the 500 error: instantiating must not assign to
    `config_entry`, which is a property on modern HA."""
    entry = types.SimpleNamespace(
        data={"_module_id": "cover_policy"}, options={}, entry_id="abc",
    )
    flow = umbrella.BennisToolboxConfigFlow.async_get_options_flow(entry)
    assert isinstance(flow, umbrella.BennisToolboxOptionsFlow)
    # Helper is lazily created — only on first step.
    assert flow._helper is None


def test_options_flow_reads_config_entry_via_property():
    """The framework binds the entry via the managed property. The
    OptionsFlow must work entirely through `self.config_entry`."""
    OF = sys.modules["homeassistant.config_entries"].OptionsFlow
    entry = types.SimpleNamespace(
        data={"_module_id": "cover_policy"}, options={}, entry_id="abc",
    )
    flow = umbrella.BennisToolboxOptionsFlow()
    # Framework wires entry afterwards via the protected attr.
    OF._bound_entry = entry
    try:
        assert flow.config_entry is entry
    finally:
        OF._bound_entry = None


@_run
async def test_options_flow_init_shows_menu_for_cover_policy():
    OF = sys.modules["homeassistant.config_entries"].OptionsFlow
    HA = sys.modules["homeassistant.core"].HomeAssistant
    entry = types.SimpleNamespace(
        data={"_module_id": "cover_policy"}, options={}, entry_id="abc",
    )
    flow = umbrella.BennisToolboxOptionsFlow()
    flow.hass = HA()
    OF._bound_entry = entry
    try:
        result = await flow.async_step_init()
    finally:
        OF._bound_entry = None
    assert result["type"] == "menu"
    assert set(result["menu_options"]) == {"sources", "profile", "runtime"}


@_run
async def test_options_flow_proxies_unknown_steps_to_helper():
    """Unknown step names (`sources`, `runtime`) must be forwarded to the
    module-supplied helper, not abort the flow."""
    OF = sys.modules["homeassistant.config_entries"].OptionsFlow
    HA = sys.modules["homeassistant.core"].HomeAssistant
    entry = types.SimpleNamespace(
        data={"_module_id": "cover_policy"}, options={}, entry_id="abc",
    )
    flow = umbrella.BennisToolboxOptionsFlow()
    flow.hass = HA()
    OF._bound_entry = entry
    try:
        # `async_step_init` first to materialise the helper.
        await flow.async_step_init()
        sources = await flow.async_step_sources({"window_state_entity": "binary_sensor.win"})
        runtime = await flow.async_step_runtime({"startup_block_seconds": 30})
    finally:
        OF._bound_entry = None
    assert sources["step_id"] == "sources"
    assert sources["user_input"] == {"window_state_entity": "binary_sensor.win"}
    assert runtime["user_input"] == {"startup_block_seconds": 30}
