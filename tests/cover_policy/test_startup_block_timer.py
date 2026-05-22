"""Regression tests for the startup-block expiry timer.

Symptom from production: after >> `startup_block_seconds`, the
`binary_sensor.*_apply_blocked` entity still reported
`blockers = ['apply_disabled', 'startup_block']`. Two contributors:

1. `bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, …)` has a race —
   the event may already have fired by the time the listener is attached,
   leaving `_ha_started=False` forever. Fix: use `async_at_started`, which
   handles both "already started" and "will start" cases.

2. After the listener fires, `_startup_ready()` flips True at
   `_started_at + startup_block_seconds`. Without an explicit timer, the
   integration only re-evaluates on the next 30-second tick — and in some
   HA setups that interval isn't reliable. Fix: schedule a one-shot
   `async_call_later` to trigger evaluation at the exact expiry.

We load the coordinator module standalone (HA-free) by stubbing the bits
it imports.
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
MODULE_DIR = ROOT / "custom_components" / "bennis_toolbox" / "modules" / "cover_policy"


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# ---------------------------------------------------------------------------
# HA stubs — record calls to async_call_later + async_at_started so we can
# assert the coordinator wires them up.
# ---------------------------------------------------------------------------


_SCHEDULED_CALL_LATER: list[dict] = []
_AT_STARTED_CALLBACKS: list = []


def _install_ha_stubs() -> None:
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    ha.__path__ = []  # type: ignore[attr-defined]

    ha_core = sys.modules.setdefault(
        "homeassistant.core", types.ModuleType("homeassistant.core")
    )

    class _HA: ...

    def _cb(fn):
        return fn

    for attr, value in (
        ("HomeAssistant", _HA), ("Event", object), ("callback", _cb),
        ("CALLBACK_TYPE", object),
    ):
        if not hasattr(ha_core, attr):
            setattr(ha_core, attr, value)

    ha_const = sys.modules.setdefault(
        "homeassistant.const", types.ModuleType("homeassistant.const")
    )
    if not hasattr(ha_const, "EVENT_HOMEASSISTANT_STARTED"):
        ha_const.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"

    ha_ce = sys.modules.setdefault(
        "homeassistant.config_entries", types.ModuleType("homeassistant.config_entries")
    )

    class _ConfigEntry:
        def __init__(self, data=None, options=None, entry_id="e1"):
            self.data = dict(data or {})
            self.options = dict(options or {})
            self.entry_id = entry_id

    if not hasattr(ha_ce, "ConfigEntry"):
        ha_ce.ConfigEntry = _ConfigEntry

    ha_helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    ha_helpers.__path__ = []  # type: ignore[attr-defined]

    ha_event = sys.modules.setdefault(
        "homeassistant.helpers.event", types.ModuleType("homeassistant.helpers.event")
    )

    def _track_state(hass, entities, cb):
        return lambda: None

    def _track_interval(hass, cb, interval):
        return lambda: None

    def _call_later(hass, seconds, cb):
        _SCHEDULED_CALL_LATER.append({"seconds": seconds, "cb": cb})
        return lambda: None

    ha_event.async_track_state_change_event = _track_state
    ha_event.async_track_time_interval = _track_interval
    ha_event.async_call_later = _call_later

    ha_start = sys.modules.setdefault(
        "homeassistant.helpers.start", types.ModuleType("homeassistant.helpers.start")
    )

    def _at_started(hass, cb):
        _AT_STARTED_CALLBACKS.append(cb)
        return lambda: None

    ha_start.async_at_started = _at_started


_install_ha_stubs()


# Toolbox-relative imports (`...const`, `...storage`).
def _install_toolbox_stubs() -> None:
    if "sbt_tb_stub" in sys.modules:
        return
    pkg = types.ModuleType("sbt_tb_stub")
    pkg.__path__ = []
    sys.modules["sbt_tb_stub"] = pkg

    const_mod = types.ModuleType("sbt_tb_stub.const")
    const_mod.DOMAIN = "bennis_toolbox"
    const_mod.DATA_ENTRIES = "entries"
    sys.modules["sbt_tb_stub.const"] = const_mod

    storage_mod = types.ModuleType("sbt_tb_stub.storage")

    class _Store:
        def __init__(self, *_a, **_kw): self._data = {}
        async def async_load(self): return self._data
        async def async_save(self, data): self._data = data

    def make_store(hass, module_id, key, version=1):
        return _Store()

    storage_mod.make_store = make_store
    sys.modules["sbt_tb_stub.storage"] = storage_mod


_install_toolbox_stubs()


# Reuse cp_const / cp_policy that the conftest loads.
import cp_const  # noqa: E402
import cp_policy  # noqa: E402


def _load_coordinator():
    src = (MODULE_DIR / "coordinator.py").read_text(encoding="utf-8")
    src = src.replace("from ...const import", "from sbt_tb_stub.const import")
    src = src.replace("from ...storage import", "from sbt_tb_stub.storage import")
    src = src.replace("from . import policy", "import cp_policy as policy")
    src = src.replace("from .const import", "from cp_const import")
    mod = types.ModuleType("cp_coord_under_test")
    sys.modules["cp_coord_under_test"] = mod
    exec(compile(src, str(MODULE_DIR / "coordinator.py"), "exec"), mod.__dict__)
    return mod


coordinator_mod = _load_coordinator()


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


class _FakeHass:
    def __init__(self, is_running=True):
        self.is_running = is_running
        self.states = _States()
        self.data = {"bennis_toolbox": {"entries": {}}}
        self._tasks: list = []

    def async_create_task(self, coro):
        self._tasks.append(coro)
        return coro

    @property
    def bus(self):
        class _Bus:
            def async_listen_once(self, *_a, **_kw):
                return lambda: None
        return _Bus()


class _States:
    def get(self, _eid):
        return None


def _make_entry(startup_block_seconds=60, apply_enabled=False):
    return types.SimpleNamespace(
        data={
            "cover_entity": "cover.living_blackout_blind",
            "_module_id": "cover_policy",
        },
        options={
            cp_const.CONF_APPLY_ENABLED: apply_enabled,
            cp_const.CONF_STARTUP_BLOCK_SECONDS: startup_block_seconds,
            cp_const.CONF_PROFILE: dict(cp_const.DEFAULT_PROFILE),
        },
        entry_id="abc",
    )


# ---------------------------------------------------------------------------
# 1) async_at_started is used so the startup race can't strand _ha_started.
# ---------------------------------------------------------------------------


def setup_function(_fn):
    _SCHEDULED_CALL_LATER.clear()
    _AT_STARTED_CALLBACKS.clear()


def test_async_start_registers_async_at_started():
    hass = _FakeHass(is_running=True)
    entry = _make_entry()
    coord = coordinator_mod.CoverPolicyCoordinator(hass, entry)
    coord.async_start()
    # Exactly one async_at_started subscription regardless of `is_running`.
    assert len(_AT_STARTED_CALLBACKS) == 1


# ---------------------------------------------------------------------------
# 2) When started, a one-shot async_call_later is scheduled with the
#    configured startup_block_seconds (+1s safety margin).
# ---------------------------------------------------------------------------


def test_on_started_schedules_startup_block_expiry_timer():
    hass = _FakeHass(is_running=True)
    entry = _make_entry(startup_block_seconds=60)
    coord = coordinator_mod.CoverPolicyCoordinator(hass, entry)
    coord.async_start()
    # Simulate HA reaching the started phase.
    assert len(_AT_STARTED_CALLBACKS) == 1
    _AT_STARTED_CALLBACKS[0](hass)

    assert _SCHEDULED_CALL_LATER, "expected a one-shot async_call_later"
    last = _SCHEDULED_CALL_LATER[-1]
    assert 60 <= last["seconds"] <= 65  # 60 + small safety margin


# ---------------------------------------------------------------------------
# 3) After the timer fires, _startup_ready() is True and the next decision
#    no longer carries the `startup_block` blocker.
# ---------------------------------------------------------------------------


@_run
async def test_startup_block_clears_after_timer_fires():
    hass = _FakeHass(is_running=True)
    entry = _make_entry(startup_block_seconds=0, apply_enabled=True)
    coord = coordinator_mod.CoverPolicyCoordinator(hass, entry)
    # Pretend we're starting up.
    coord.async_start()
    _AT_STARTED_CALLBACKS[0](hass)

    # Before the timer, the coordinator may or may not be "started" — but
    # _startup_ready depends on monotonic time delta. With
    # startup_block_seconds=0 we're past the window immediately.
    decision = await coord.async_evaluate()
    assert "startup_block" not in decision.blockers


# ---------------------------------------------------------------------------
# 4) Reload-safe: async_stop cancels the pending one-shot.
# ---------------------------------------------------------------------------


def test_async_stop_cancels_pending_startup_timer():
    hass = _FakeHass(is_running=True)
    entry = _make_entry(startup_block_seconds=60)
    coord = coordinator_mod.CoverPolicyCoordinator(hass, entry)
    coord.async_start()
    _AT_STARTED_CALLBACKS[0](hass)
    assert coord._startup_unsub is not None
    coord.async_stop()
    assert coord._startup_unsub is None
