"""Config / service / entity smoke tests for stash_ha.

Same pattern as the other modules: stub HA + toolbox-root, then load
flow.py / services_impl.py / webhook.py via source-rewrite so we can
exercise them without a real Home Assistant.
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
) / "custom_components" / "bennis_toolbox" / "modules" / "stash_ha"


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# =========================================================================
# Stubs (idempotent — earlier test files in the same pytest run may have
# installed a subset of these).
# =========================================================================


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
        def __init__(self, **kw): self.kw = kw

    class _ES:
        def __init__(self, cfg=None): self.cfg = cfg
        def __call__(self, v): return v

    class _SSCfg:
        def __init__(self, **kw): self.kw = kw

    class _SS:
        def __init__(self, cfg=None): self.cfg = cfg
        def __call__(self, v): return v

    class _SSMode:
        LIST = "list"
        DROPDOWN = "dropdown"

    class _TSCfg:
        def __init__(self, **kw): self.kw = kw

    class _TS:
        def __init__(self, cfg=None): self.cfg = cfg
        def __call__(self, v): return v

    class _OS:
        def __call__(self, v): return v

    for attr, value in (
        ("EntitySelector", _ES), ("EntitySelectorConfig", _ESCfg),
        ("SelectSelector", _SS), ("SelectSelectorConfig", _SSCfg),
        ("SelectSelectorMode", _SSMode),
        ("TextSelector", _TS), ("TextSelectorConfig", _TSCfg),
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

    # aiohttp_client.async_get_clientsession — flow.py uses it during
    # validate(). We supply a fake session that we can inject from the test.
    ha_aio = sys.modules.setdefault(
        "homeassistant.helpers.aiohttp_client",
        types.ModuleType("homeassistant.helpers.aiohttp_client"),
    )
    if not hasattr(ha_aio, "async_get_clientsession"):
        ha_aio.async_get_clientsession = lambda hass: getattr(hass, "_fake_session", None)

    # HomeAssistantView shell for webhook.py.
    ha_http = sys.modules.setdefault(
        "homeassistant.components", types.ModuleType("homeassistant.components")
    )
    ha_http.__path__ = getattr(ha_http, "__path__", [])
    ha_http_pkg = sys.modules.setdefault(
        "homeassistant.components.http",
        types.ModuleType("homeassistant.components.http"),
    )

    class _HAView:
        requires_auth = False

    if not hasattr(ha_http_pkg, "HomeAssistantView"):
        ha_http_pkg.HomeAssistantView = _HAView

    # aiohttp.web — webhook.py only needs the `web` namespace for typing.
    aiohttp_mod = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    aiohttp_web = sys.modules.setdefault("aiohttp.web", types.ModuleType("aiohttp.web"))

    class _FakeRequest: ...
    class _FakeResponse: ...

    if not hasattr(aiohttp_web, "Request"):
        aiohttp_web.Request = _FakeRequest
    if not hasattr(aiohttp_web, "Response"):
        aiohttp_web.Response = _FakeResponse
    if not hasattr(aiohttp_mod, "web"):
        aiohttp_mod.web = aiohttp_web


_install_ha_stubs()


def _install_toolbox_stubs() -> None:
    if "sh_toolbox_stub" in sys.modules:
        return
    pkg = types.ModuleType("sh_toolbox_stub")
    pkg.__path__ = []
    sys.modules["sh_toolbox_stub"] = pkg

    const_mod = types.ModuleType("sh_toolbox_stub.const")
    const_mod.CONF_MODULE_ID = "_module_id"
    const_mod.DOMAIN = "bennis_toolbox"
    const_mod.DATA_ENTRIES = "entries"
    sys.modules["sh_toolbox_stub.const"] = const_mod

    services_mod = types.ModuleType("sh_toolbox_stub.services")

    class _ServiceDef:
        def __init__(self, handler, schema=None):
            self.handler = handler
            self.schema = schema

    services_mod.ServiceDef = _ServiceDef
    sys.modules["sh_toolbox_stub.services"] = services_mod


_install_toolbox_stubs()


# Coordinator stub: keep services_impl.py from dragging in the real
# coordinator (which imports DataUpdateCoordinator).
def _install_coordinator_stub() -> None:
    if "sh_coordinator_stub" in sys.modules:
        return
    mod = types.ModuleType("sh_coordinator_stub")

    def all_stash_runtimes(hass):
        out = []
        for bucket in hass.data.get("bennis_toolbox", {}).get("entries", {}).values():
            if bucket.get("module_id") != "stash_ha":
                continue
            rt = bucket.get("runtime")
            if rt is not None:
                out.append(rt)
        return out

    def runtime_from_hass(hass, entry_id):
        bucket = hass.data.get("bennis_toolbox", {}).get("entries", {}).get(entry_id)
        return bucket.get("runtime") if bucket else None

    class _StubLibraryCoordinator: ...
    class _StubPlaybackCoordinator: ...

    mod.all_stash_runtimes = all_stash_runtimes
    mod.runtime_from_hass = runtime_from_hass
    mod.StashLibraryCoordinator = _StubLibraryCoordinator
    mod.StashPlaybackCoordinator = _StubPlaybackCoordinator
    sys.modules["sh_coordinator_stub"] = mod


_install_coordinator_stub()


# Reuse pure const + client from the existing conftest layer.
import sh_const  # noqa: E402
import sh_client  # noqa: E402


def _load_with_remaps(filename: str, new_name: str):
    src = (MODULE_DIR / filename).read_text(encoding="utf-8")
    src = src.replace("from ...const import", "from sh_toolbox_stub.const import")
    src = src.replace("from ...services import", "from sh_toolbox_stub.services import")
    src = src.replace("from .const import", "from sh_const import")
    src = src.replace("from .client import", "from sh_client import")
    src = src.replace("from .coordinator import", "from sh_coordinator_stub import")
    mod = types.ModuleType(new_name)
    sys.modules[new_name] = mod
    exec(compile(src, str(MODULE_DIR / filename), "exec"), mod.__dict__)
    return mod


flow_module = _load_with_remaps("flow.py", "sh_flow")
services_module = _load_with_remaps("services_impl.py", "sh_services_impl")
webhook_module = _load_with_remaps("webhook.py", "sh_webhook")


# =========================================================================
# 1) Entity-Key contract (AST + const lookup).
# =========================================================================


def _extract_uid_constants_used(source: str, const_module) -> set[str]:
    """Collect every UID_*-style suffix string the entities module references.

    Two flavours:
    1. `unique_id(MODULE_ID, entry.entry_id, UID_FOO)` — `UID_FOO` is a Name
       referencing const.py. Resolve its value.
    2. `_LibCountSensor(..., UID_BAR, "Name", ...)` — the suffix is a
       positional argument passed in to a helper that itself calls
       unique_id(). We recognise those by walking the call args and
       resolving any Name that maps to a UID_* string on const.py.
    """
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id.startswith("UID_"):
                val = getattr(const_module, arg.id, None)
                if isinstance(val, str):
                    out.add(val)
            elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                # Only count string literals that are passed alongside a
                # MODULE_ID/entry context to unique_id(...).
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "unique_id"
                    and len(node.args) >= 3
                    and node.args[-1] is arg
                ):
                    out.add(arg.value)
    return out


def test_entities_expose_all_15_unique_id_suffixes():
    src = (MODULE_DIR / "entities.py").read_text(encoding="utf-8")
    suffixes = _extract_uid_constants_used(src, sh_const)
    expected = {
        # library
        "scenes_count", "movies_count", "performers_count", "studios_count",
        "tags_count", "images_count", "galleries_count", "markers_count",
        "version",
        # playback
        "active_streams", "currently_playing", "last_played_title", "last_played_at",
        # image + media_player
        "cover", "player",
    }
    assert suffixes == expected, suffixes


# =========================================================================
# 2) Webhook URL contract.
# =========================================================================


def test_webhook_url_uses_toolbox_prefixed_path():
    assert webhook_module.webhook_url("abc") == "/api/bennis_toolbox/stash_ha/webhook/abc"


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

    async def async_set_unique_id(self, v):
        self.unique_id = v

    def _abort_if_unique_id_configured(self):
        if self.already_configured:
            raise _AbortFlowError("already configured")

    def async_show_form(self, step_id, data_schema=None, errors=None, **_kw):
        self.last_form = {
            "step_id": step_id,
            "errors": dict(errors or {}),
        }
        return {"type": "form", "step_id": step_id, "errors": dict(errors or {})}

    def async_create_entry(self, title, data, options=None):
        self.created_entry = {
            "type": "create_entry",
            "title": title,
            "data": dict(data),
            "options": dict(options or {}),
        }
        return self.created_entry


class _OkClient:
    def __init__(self, *_a, **_kw): pass
    async def validate(self): return None


class _FailClient:
    def __init__(self, *_a, **_kw): pass
    async def validate(self):
        raise sh_client.StashError("nope")


class _FakeHass:
    _fake_session = object()
    data: dict = {}


@_run
async def test_config_flow_init_shows_form_without_unique_id():
    flow = _FakeFlow()
    helper = flow_module.ConfigFlowHelper(hass=_FakeHass(), flow=flow)
    result = await helper.async_step_init()
    assert result["step_id"] == "module_step"
    assert flow.unique_id is None


@_run
async def test_config_flow_creates_entry_with_normalised_url(monkeypatch):
    flow = _FakeFlow()
    helper = flow_module.ConfigFlowHelper(hass=_FakeHass(), flow=flow)
    await helper.async_step_init()
    monkeypatch.setattr(flow_module, "StashClient", _OkClient)
    result = await helper.async_step_module_step({
        "url": "https://stash.example/",
        "api_key": "secret",
        "player_name": "Stash",
        "poll_interval": 5,
        "use_webhook": True,
        "nsfw_mode": "blur",
    })
    assert result["type"] == "create_entry"
    assert flow.unique_id == "stash_ha:https://stash.example/graphql"
    assert result["data"]["_module_id"] == "stash_ha"
    assert result["data"]["url"] == "https://stash.example/graphql"
    assert result["data"]["api_key"] == "secret"
    assert result["options"]["poll_interval"] == 5
    assert result["options"]["use_webhook"] is True


@_run
async def test_config_flow_rejects_empty_url(monkeypatch):
    flow = _FakeFlow()
    helper = flow_module.ConfigFlowHelper(hass=_FakeHass(), flow=flow)
    await helper.async_step_init()
    monkeypatch.setattr(flow_module, "StashClient", _OkClient)
    result = await helper.async_step_module_step({"url": "   "})
    assert result["type"] == "form"
    assert result["errors"]["url"] == "invalid_url"
    assert flow.created_entry is None


@_run
async def test_config_flow_handles_validation_failure(monkeypatch):
    flow = _FakeFlow()
    helper = flow_module.ConfigFlowHelper(hass=_FakeHass(), flow=flow)
    await helper.async_step_init()
    monkeypatch.setattr(flow_module, "StashClient", _FailClient)
    result = await helper.async_step_module_step({"url": "https://x"})
    assert result["type"] == "form"
    assert result["errors"]["base"] == "cannot_connect"
    assert flow.created_entry is None


@_run
async def test_config_flow_aborts_on_duplicate_url(monkeypatch):
    flow = _FakeFlow(already_configured=True)
    helper = flow_module.ConfigFlowHelper(hass=_FakeHass(), flow=flow)
    await helper.async_step_init()
    monkeypatch.setattr(flow_module, "StashClient", _OkClient)
    with pytest.raises(_AbortFlowError):
        await helper.async_step_module_step({"url": "https://x"})


# =========================================================================
# 4) Service-smoke.
# =========================================================================


def test_services_have_expected_seven_actions():
    assert set(services_module.SERVICES.keys()) == {
        "metadata_scan", "metadata_clean", "metadata_generate",
        "metadata_auto_tag", "metadata_identify",
        "generate_screenshot", "save_activity",
    }


def test_generate_screenshot_schema_requires_scene_id():
    schema = services_module.SERVICES["generate_screenshot"].schema
    with pytest.raises(vol.Invalid):
        schema({})
    assert schema({"scene_id": "42"})["scene_id"] == "42"


def test_save_activity_schema_requires_scene_id_and_positive_position():
    schema = services_module.SERVICES["save_activity"].schema
    with pytest.raises(vol.Invalid):
        schema({"scene_id": "42"})  # missing position
    with pytest.raises(vol.Invalid):
        schema({"scene_id": "42", "position": -1})
    parsed = schema({"scene_id": "42", "position": "12.5"})
    assert parsed["scene_id"] == "42"
    assert parsed["position"] == 12.5


class _RecClient:
    def __init__(self):
        self.scans = 0
        self.cleans = 0
        self.generates = 0
        self.auto_tags = 0
        self.identifies = 0
        self.screenshots: list[str] = []
        self.activities: list[tuple[str, float]] = []

    async def metadata_scan(self): self.scans += 1
    async def metadata_clean(self): self.cleans += 1
    async def metadata_generate(self): self.generates += 1
    async def metadata_auto_tag(self): self.auto_tags += 1
    async def metadata_identify(self): self.identifies += 1

    async def generate_screenshot(self, scene_id):
        self.screenshots.append(scene_id)

    async def save_activity(self, scene_id, position):
        self.activities.append((scene_id, position))


class _RecCoord:
    def __init__(self):
        self.refresh_calls = 0

    async def async_request_refresh(self):
        self.refresh_calls += 1


def _make_hass_with_stash(client: _RecClient, playback: _RecCoord, *, foreign=False):
    hass = types.SimpleNamespace()
    hass.data = {"bennis_toolbox": {"entries": {}}}
    hass.data["bennis_toolbox"]["entries"]["e1"] = {
        "module_id": "stash_ha",
        "runtime": {"client": client, "playback": playback, "library": object()},
    }
    if foreign:
        hass.data["bennis_toolbox"]["entries"]["e2"] = {
            "module_id": "plug_policy_engine",
            "runtime": {"client": _RecClient(), "playback": _RecCoord()},
        }
    return hass


@_run
async def test_metadata_scan_fans_out_only_to_stash_clients():
    client = _RecClient()
    coord = _RecCoord()
    hass = _make_hass_with_stash(client, coord, foreign=True)
    await services_module.SERVICES["metadata_scan"].handler(hass, types.SimpleNamespace(data={}))
    assert client.scans == 1
    # The sibling plug_policy_engine runtime must be ignored.
    foreign_client = hass.data["bennis_toolbox"]["entries"]["e2"]["runtime"]["client"]
    assert foreign_client.scans == 0


@_run
async def test_metadata_actions_each_route_to_their_client_method():
    client = _RecClient()
    coord = _RecCoord()
    hass = _make_hass_with_stash(client, coord)
    for action, attr in (
        ("metadata_scan", "scans"),
        ("metadata_clean", "cleans"),
        ("metadata_generate", "generates"),
        ("metadata_auto_tag", "auto_tags"),
        ("metadata_identify", "identifies"),
    ):
        await services_module.SERVICES[action].handler(hass, types.SimpleNamespace(data={}))
        assert getattr(client, attr) == 1, action


@_run
async def test_generate_screenshot_triggers_coordinator_refresh():
    client = _RecClient()
    coord = _RecCoord()
    hass = _make_hass_with_stash(client, coord)
    await services_module.SERVICES["generate_screenshot"].handler(
        hass, types.SimpleNamespace(data={"scene_id": "42"})
    )
    assert client.screenshots == ["42"]
    assert coord.refresh_calls == 1


@_run
async def test_save_activity_calls_client_and_refreshes():
    client = _RecClient()
    coord = _RecCoord()
    hass = _make_hass_with_stash(client, coord)
    await services_module.SERVICES["save_activity"].handler(
        hass, types.SimpleNamespace(data={"scene_id": "42", "position": 17.5})
    )
    assert client.activities == [("42", 17.5)]
    assert coord.refresh_calls == 1
