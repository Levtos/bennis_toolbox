"""Config/service/entity/coordinator smoke tests for notification_router.

Pattern mirrors benni_media_context and plug_policy_engine: stub HA + the
toolbox-root package, then load flow.py / services_impl.py / coordinator.py
via source-rewrite so they can be exercised without a real HA install.
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
) / "custom_components" / "bennis_toolbox" / "modules" / "notification_router"


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# =========================================================================
# Stubs
# =========================================================================


def _install_ha_stubs() -> None:
    # Idempotent per submodule via setdefault — earlier test files in the
    # same pytest run may already have installed a subset of these.
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
        ("HomeAssistant", _HA),
        ("ServiceCall", _Call),
        ("callback", _cb),
        ("Event", object),
    ):
        if not hasattr(ha_core, attr):
            setattr(ha_core, attr, value)

    ha_ce = sys.modules.setdefault(
        "homeassistant.config_entries", types.ModuleType("homeassistant.config_entries")
    )

    class _ConfigEntry:
        def __init__(self, data=None, options=None, entry_id="test-entry"):
            self.data = data or {}
            self.options = options or {}
            self.entry_id = entry_id

    class _OptionsFlow: ...

    if not hasattr(ha_ce, "ConfigEntry"):
        ha_ce.ConfigEntry = _ConfigEntry
    if not hasattr(ha_ce, "OptionsFlow"):
        ha_ce.OptionsFlow = _OptionsFlow

    ha_def = sys.modules.setdefault(
        "homeassistant.data_entry_flow", types.ModuleType("homeassistant.data_entry_flow")
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
        def __init__(self, **kw):
            self.kw = kw

    class _ES:
        def __init__(self, cfg=None): self.cfg = cfg
        def __call__(self, v): return v

    class _TSCfg:
        def __init__(self, **kw):
            self.kw = kw

    class _TS:
        def __init__(self, cfg=None): self.cfg = cfg
        def __call__(self, v): return v

    class _OS:
        def __call__(self, v): return v

    for attr, value in (
        ("EntitySelector", _ES),
        ("EntitySelectorConfig", _ESCfg),
        ("TextSelector", _TS),
        ("TextSelectorConfig", _TSCfg),
        ("ObjectSelector", _OS),
    ):
        if not hasattr(ha_sel, attr):
            setattr(ha_sel, attr, value)

    ha_cv = sys.modules.setdefault(
        "homeassistant.helpers.config_validation",
        types.ModuleType("homeassistant.helpers.config_validation"),
    )
    if not hasattr(ha_cv, "string"):
        ha_cv.string = lambda v: str(v)

    # Dispatcher — coordinator.py imports this.
    ha_disp = sys.modules.setdefault(
        "homeassistant.helpers.dispatcher",
        types.ModuleType("homeassistant.helpers.dispatcher"),
    )
    if not hasattr(ha_disp, "async_dispatcher_send"):
        ha_disp.async_dispatcher_send = lambda hass, signal, *a, **kw: None
    if not hasattr(ha_disp, "async_dispatcher_connect"):
        ha_disp.async_dispatcher_connect = lambda hass, signal, target: (lambda: None)


_install_ha_stubs()


def _install_toolbox_stubs() -> None:
    if "nr_toolbox_stub" in sys.modules:
        return
    pkg = types.ModuleType("nr_toolbox_stub")
    pkg.__path__ = []
    sys.modules["nr_toolbox_stub"] = pkg

    const_mod = types.ModuleType("nr_toolbox_stub.const")
    const_mod.CONF_MODULE_ID = "_module_id"
    const_mod.DOMAIN = "bennis_toolbox"
    const_mod.DATA_ENTRIES = "entries"
    sys.modules["nr_toolbox_stub.const"] = const_mod

    services_mod = types.ModuleType("nr_toolbox_stub.services")

    class _ServiceDef:
        def __init__(self, handler, schema=None):
            self.handler = handler
            self.schema = schema

    services_mod.ServiceDef = _ServiceDef
    sys.modules["nr_toolbox_stub.services"] = services_mod

    # The real ...storage module exposes make_store; coordinator.py uses it.
    storage_mod = types.ModuleType("nr_toolbox_stub.storage")

    class _FakeStore:
        def __init__(self, *_a, **_kw):
            self._data: dict | None = None

        async def async_load(self):
            return self._data

        async def async_save(self, data):
            self._data = data

    def make_store(hass, module_id, suffix, *, version=1):
        return _FakeStore()

    storage_mod.make_store = make_store
    sys.modules["nr_toolbox_stub.storage"] = storage_mod


_install_toolbox_stubs()


# A coordinator stub for services_impl.py so it doesn't drag in coordinator.py
# (which imports HA helpers we already stub). The real module does the same
# kind of lookup based on hass.data — we replicate that here.
def _install_coordinator_stub() -> None:
    if "nr_coordinator_stub" in sys.modules:
        return
    mod = types.ModuleType("nr_coordinator_stub")

    def all_notification_routers(hass):
        out = []
        for bucket in hass.data.get("bennis_toolbox", {}).get("entries", {}).values():
            if bucket.get("module_id") != "notification_router":
                continue
            r = bucket.get("router")
            if r is not None:
                out.append(r)
        return out

    def router_from_hass(hass, entry_id):
        bucket = hass.data.get("bennis_toolbox", {}).get("entries", {}).get(entry_id)
        return bucket.get("router") if bucket else None

    class _StubRouter: ...

    mod.all_notification_routers = all_notification_routers
    mod.router_from_hass = router_from_hass
    mod.NotificationRouter = _StubRouter
    mod.SIGNAL_STATE_UPDATED = "bennis_toolbox_notification_router_state_updated"
    sys.modules["nr_coordinator_stub"] = mod


_install_coordinator_stub()


# Reuse pure const from the existing conftest layer.
import nr_const  # noqa: E402
import nr_routing  # noqa: E402


def _load_with_remaps(filename: str, new_name: str):
    src = (MODULE_DIR / filename).read_text(encoding="utf-8")
    src = src.replace("from ...const import", "from nr_toolbox_stub.const import")
    src = src.replace("from ...services import", "from nr_toolbox_stub.services import")
    src = src.replace("from ...storage import", "from nr_toolbox_stub.storage import")
    src = src.replace("from .const import", "from nr_const import")
    src = src.replace("from .routing import", "from nr_routing import")
    src = src.replace("from .coordinator import", "from nr_coordinator_stub import")
    mod = types.ModuleType(new_name)
    sys.modules[new_name] = mod
    exec(compile(src, str(MODULE_DIR / filename), "exec"), mod.__dict__)
    return mod


flow_module = _load_with_remaps("flow.py", "nr_flow")
services_module = _load_with_remaps("services_impl.py", "nr_services_impl")
coordinator_module = _load_with_remaps("coordinator.py", "nr_coordinator")


# =========================================================================
# 1) Entity-Key contract via AST scan.
# =========================================================================


def _extract_unique_id_suffix_values(source: str, const_module) -> set[str]:
    """Find every literal/name suffix passed to unique_id(MODULE_ID, ..., X).

    `X` may be a string literal (e.g. "summary") or a Name referencing a
    constant on const.py — we resolve those via the supplied const_module.
    """
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "unique_id"
        ):
            continue
        if not node.args:
            continue
        last = node.args[-1]
        if isinstance(last, ast.Constant) and isinstance(last.value, str):
            out.add(last.value)
        elif isinstance(last, ast.Name):
            val = getattr(const_module, last.id, None)
            if isinstance(val, str):
                out.add(val)
    return out


def test_entities_expose_three_expected_unique_id_suffixes():
    src = (MODULE_DIR / "entities.py").read_text(encoding="utf-8")
    suffixes = _extract_unique_id_suffix_values(src, nr_const)
    # const.py: SENSOR_MODE="mode", SENSOR_LAST_EVENT="last_event",
    # BINARY_SENSOR_DND="dnd_active".
    assert suffixes == {"mode", "last_event", "dnd_active"}, suffixes


# =========================================================================
# 2) Config-flow smoke.
# =========================================================================


class _AbortFlowError(Exception): ...


class _FakeFlow:
    def __init__(self, already_configured=False):
        self.already_configured = already_configured
        self.unique_id = None
        self.last_form = None
        self.created_entry = None

    async def async_set_unique_id(self, v):
        self.unique_id = v

    def _abort_if_unique_id_configured(self):
        if self.already_configured:
            raise _AbortFlowError("already configured")

    def async_show_form(self, step_id, data_schema=None, **_kw):
        self.last_form = {"step_id": step_id}
        return {"type": "form", "step_id": step_id}

    def async_create_entry(self, title, data, options=None):
        self.created_entry = {
            "type": "create_entry",
            "title": title, "data": dict(data),
            "options": dict(options or {}),
        }
        return self.created_entry


@_run
async def test_config_flow_init_sets_singleton_and_shows_form():
    flow = _FakeFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    result = await helper.async_step_init()
    assert flow.unique_id == "notification_router_singleton"
    assert result["step_id"] == "module_step"


@_run
async def test_config_flow_aborts_second_instance():
    flow = _FakeFlow(already_configured=True)
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    with pytest.raises(_AbortFlowError):
        await helper.async_step_init()


@_run
async def test_config_flow_creates_entry_with_module_id_and_drops_empty_slots():
    flow = _FakeFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    await helper.async_step_init()
    result = await helper.async_step_module_step({
        "bio_state_entity": "sensor.bio_state",
        "activity_state_entity": "",
        "presence_personal_entity": "sensor.presence",
        "notify_targets": ["notify.mobile_app_a", "notify.mobile_app_b"],
        "headset_active_entity": None,
    })
    assert result["data"]["_module_id"] == "notification_router"
    assert result["data"]["bio_state_entity"] == "sensor.bio_state"
    assert result["data"]["presence_personal_entity"] == "sensor.presence"
    assert result["data"]["notify_targets"] == ["notify.mobile_app_a", "notify.mobile_app_b"]
    assert "activity_state_entity" not in result["data"]
    assert "headset_active_entity" not in result["data"]


# =========================================================================
# 3) Service-smoke.
# =========================================================================


def test_services_have_the_three_expected_actions():
    assert set(services_module.SERVICES.keys()) == {"route", "clear", "set_dnd"}


def test_route_schema_requires_event_type():
    schema = services_module.SERVICES["route"].schema
    with pytest.raises(vol.Invalid):
        schema({})
    parsed = schema({"event_type": "doorbell"})
    assert parsed["severity"] == "normal"  # default
    assert parsed["title"] == ""


def test_route_schema_rejects_unknown_event_type():
    schema = services_module.SERVICES["route"].schema
    with pytest.raises(vol.Invalid):
        schema({"event_type": "made_up_class"})


def test_set_dnd_schema_clamps_to_valid_range():
    schema = services_module.SERVICES["set_dnd"].schema
    assert schema({})["duration"] == 0
    with pytest.raises(vol.Invalid):
        schema({"duration": -1})
    with pytest.raises(vol.Invalid):
        schema({"duration": 99_999})


class _RecRouter:
    def __init__(self):
        self.routes: list[dict] = []
        self.clears: list[str | None] = []
        self.dnd_set: list[int | None] = []

    async def async_route(self, **kw):
        self.routes.append(kw)

    async def async_clear(self, dedupe_key=None):
        self.clears.append(dedupe_key)

    async def async_set_dnd(self, duration):
        self.dnd_set.append(duration)


class _FakeHass:
    def __init__(self):
        self.data = {"bennis_toolbox": {"entries": {}}}


class _FakeCall:
    def __init__(self, data=None):
        self.data = data or {}


@_run
async def test_route_service_fans_out_to_only_notification_router_coordinators():
    hass = _FakeHass()
    mine = _RecRouter()
    foreign = _RecRouter()
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "notification_router", "router": mine,
    }
    hass.data["bennis_toolbox"]["entries"]["e2"] = {
        "module_id": "plug_policy_engine", "router": foreign,
    }
    await services_module.SERVICES["route"].handler(
        hass, _FakeCall({
            "event_type": "doorbell",
            "severity": "urgent",
            "title": "Ding",
            "message": "Bell",
            "payload": {"who": "guest"},
            "dedupe_key": "k1",
        }),
    )
    assert len(mine.routes) == 1
    assert mine.routes[0]["event_type"] == "doorbell"
    assert mine.routes[0]["severity"] == "urgent"
    assert mine.routes[0]["dedupe_key"] == "k1"
    assert mine.routes[0]["payload"] == {"who": "guest"}
    # The plug_policy_engine sibling must have been ignored.
    assert foreign.routes == []


@_run
async def test_clear_passes_dedupe_key_when_given():
    hass = _FakeHass()
    rt = _RecRouter()
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "notification_router", "router": rt,
    }
    await services_module.SERVICES["clear"].handler(hass, _FakeCall({"dedupe_key": "x"}))
    await services_module.SERVICES["clear"].handler(hass, _FakeCall())
    assert rt.clears == ["x", None]


@_run
async def test_set_dnd_translates_zero_to_none():
    hass = _FakeHass()
    rt = _RecRouter()
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "notification_router", "router": rt,
    }
    await services_module.SERVICES["set_dnd"].handler(hass, _FakeCall({"duration": 0}))
    await services_module.SERVICES["set_dnd"].handler(hass, _FakeCall({"duration": 60}))
    assert rt.dnd_set == [None, 60]


# =========================================================================
# 4) Coordinator smoke — exercise the real NotificationRouter against a
#    fake hass + states. No HA-internals beyond what we stubbed above.
# =========================================================================


class _FakeState:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class _StatesView:
    def __init__(self, table):
        self._t = table

    def get(self, entity_id):
        return self._t.get(entity_id)


class _Bus:
    def __init__(self):
        self.fired: list[tuple[str, dict]] = []

    def async_fire(self, event, data):
        self.fired.append((event, data))


class _Services:
    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    async def async_call(self, domain, name, data, blocking=False):
        self.calls.append((domain, name, dict(data)))


class _CoordHass:
    def __init__(self, states=None):
        self.states = _StatesView(states or {})
        self.bus = _Bus()
        self.services = _Services()


def _make_router(states=None, data=None, options=None) -> object:
    hass = _CoordHass(states or {})
    router = coordinator_module.NotificationRouter(
        hass, entry_id="e1",
        entry_data=data or {},
        options=options or {},
    )
    return router


@_run
async def test_router_route_fires_toolbox_prefixed_event():
    router = _make_router()
    await router.async_load()
    decision = await router.async_route(
        event_type="doorbell", title="Ding", message="Bell", dedupe_key="k1",
    )
    assert decision.routes  # not empty
    hass = router.hass
    assert len(hass.bus.fired) == 1
    event_name, payload = hass.bus.fired[0]
    assert event_name == "bennis_toolbox_notification_router_routed"
    assert payload["event_type"] == "doorbell"
    assert payload["dedupe_key"] == "k1"


@_run
async def test_router_dedupe_suppresses_repeat_within_window():
    router = _make_router()
    await router.async_load()
    first = await router.async_route(event_type="info", dedupe_key="x")
    second = await router.async_route(event_type="info", dedupe_key="x")
    assert "suppressed" not in first.reason
    assert "dedupe_key=x within window" in second.reason


@_run
async def test_router_rate_limit_suppresses_after_cap():
    router = _make_router(options={"rate_limit_per_minute": 2})
    await router.async_load()
    a = await router.async_route(event_type="info", dedupe_key="a")
    b = await router.async_route(event_type="info", dedupe_key="b")
    c = await router.async_route(event_type="info", dedupe_key="c")
    assert "rate limit" not in a.reason
    assert "rate limit" not in b.reason
    assert "rate limit exceeded" in c.reason


@_run
async def test_router_dnd_set_and_clear():
    router = _make_router()
    await router.async_load()
    assert router.dnd_active() is False
    await router.async_set_dnd(60)
    assert router.dnd_active() is True
    await router.async_set_dnd(None)
    assert router.dnd_active() is False


@_run
async def test_router_build_context_reads_entity_states():
    states = {
        "sensor.bio": _FakeState("sleep"),
        "sensor.act": _FakeState("private_time"),
        "sensor.pres": _FakeState("bei_eltern"),
        "binary_sensor.headset": _FakeState("on"),
        "binary_sensor.quiet": _FakeState("off"),
        "sensor.batt": _FakeState("12.5"),
    }
    router = _make_router(states=states, data={
        "bio_state_entity": "sensor.bio",
        "activity_state_entity": "sensor.act",
        "presence_personal_entity": "sensor.pres",
        "headset_active_entity": "binary_sensor.headset",
        "quiet_mode_active_entity": "binary_sensor.quiet",
        "lock_battery_entity": "sensor.batt",
    })
    await router.async_load()
    ctx = router.build_context()
    assert ctx.bio_state == "sleep"
    assert ctx.activity_state == "private_time"
    assert ctx.presence == "bei_eltern"
    assert ctx.headset_active is True
    assert ctx.quiet_mode_active is False
    assert ctx.lock_battery_low is True
