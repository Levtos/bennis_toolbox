"""Regression for v0.3.6 setup crash:
``TypeError: cannot use 'list' as a dict key (unhashable type: 'list')``

Existing entries — especially Einhornzentrale's — store the legacy
`homepods` slot as a list, and a single-entity slot like
`homepods_player_entity` may still arrive list-shaped on a migrated
entry. The coordinator's setup tracker collected those raw values into
`entities` and then deduped via `dict.fromkeys(entities)`, which
crashed.

These tests load the coordinator module standalone (HA-free stubs) and
exercise the new `_flatten_entities` / `_first_entity` helpers plus the
single-/multi-entity accessors.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest


MODULE_DIR = Path(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
) / "custom_components" / "bennis_toolbox" / "modules" / "benni_media_context"


def _load_orchestrator_stub():
    """Load the orchestrator module under the `bmc_orchestrator` alias so
    the test-time exec of coordinator.py can resolve its import."""
    if "bmc_orchestrator" in sys.modules:
        return
    src = (MODULE_DIR / "orchestrator.py").read_text(encoding="utf-8")
    src = src.replace("from .const import", "from bmc_const import")
    src = src.replace("from .logic import", "from bmc_logic import")
    mod = types.ModuleType("bmc_orchestrator")
    sys.modules["bmc_orchestrator"] = mod
    exec(compile(src, str(MODULE_DIR / "orchestrator.py"), "exec"), mod.__dict__)


def _load_volume_orchestrator_stub():
    """Same trick as _load_orchestrator_stub but for the volume sibling."""
    if "bmc_volume_orchestrator" in sys.modules:
        return
    src = (MODULE_DIR / "volume_orchestrator.py").read_text(encoding="utf-8")
    src = src.replace("from .const import", "from bmc_const import")
    mod = types.ModuleType("bmc_volume_orchestrator")
    sys.modules["bmc_volume_orchestrator"] = mod
    exec(compile(src, str(MODULE_DIR / "volume_orchestrator.py"), "exec"), mod.__dict__)


def _load_coordinator():
    """Load coordinator.py with minimal HA stubs so the helpers can run.

    We only need the module-level helper functions
    (`_flatten_entities`, `_first_entity`) — the coordinator class
    itself isn't instantiated here. That keeps the test focused on
    the regression: anything list-shaped must collapse cleanly.
    """
    if "bmc_coord_for_flatten" in sys.modules:
        return sys.modules["bmc_coord_for_flatten"]

    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    ha.__path__ = []

    for name in (
        "homeassistant.core", "homeassistant.config_entries",
        "homeassistant.helpers", "homeassistant.helpers.event",
        "homeassistant.helpers.update_coordinator",
    ):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            if name.endswith(("helpers", "components")):
                mod.__path__ = []
            sys.modules[name] = mod

    ha_core = sys.modules["homeassistant.core"]
    if not hasattr(ha_core, "HomeAssistant"):
        ha_core.HomeAssistant = type("_HA", (), {})
    if not hasattr(ha_core, "callback"):
        ha_core.callback = lambda fn: fn
    if not hasattr(ha_core, "Event"):
        ha_core.Event = object
    if not hasattr(ha_core, "ServiceCall"):
        class _SC:
            def __init__(self, data=None): self.data = data or {}
        ha_core.ServiceCall = _SC

    ha_ce = sys.modules["homeassistant.config_entries"]
    if not hasattr(ha_ce, "ConfigEntry"):
        class _CE:
            def __init__(self, data=None, options=None):
                self.data = data or {}
                self.options = options or {}
                self.entry_id = "e"
        ha_ce.ConfigEntry = _CE

    ha_event = sys.modules["homeassistant.helpers.event"]
    if not hasattr(ha_event, "async_track_state_change_event"):
        ha_event.async_track_state_change_event = lambda *_a, **_kw: (lambda: None)

    ha_uc = sys.modules["homeassistant.helpers.update_coordinator"]
    if not hasattr(ha_uc, "DataUpdateCoordinator"):
        class _DUC:
            def __init__(self, *_a, **_kw): self.data = None
            def async_set_updated_data(self, d): self.data = d
            def __class_getitem__(cls, item): return cls
        ha_uc.DataUpdateCoordinator = _DUC
    if not hasattr(ha_uc, "UpdateFailed"):
        ha_uc.UpdateFailed = type("UpdateFailed", (Exception,), {})

    # homeassistant.util.dt
    sys.modules.setdefault("homeassistant.util", types.ModuleType("homeassistant.util"))
    sys.modules["homeassistant.util"].__path__ = []
    ha_dt = sys.modules.setdefault(
        "homeassistant.util.dt", types.ModuleType("homeassistant.util.dt"),
    )
    import datetime as _dt
    if not hasattr(ha_dt, "utcnow"):
        ha_dt.utcnow = lambda: _dt.datetime.now(_dt.timezone.utc)
    if not hasattr(ha_dt, "as_local"):
        ha_dt.as_local = lambda v: v

    # Read the source and rewrite the relative-import head to a flat
    # synthetic package that we can satisfy with our existing bmc_*
    # stubs from test_module_smoke.
    src = (MODULE_DIR / "coordinator.py").read_text(encoding="utf-8")
    src = src.replace("from ...const import", "from bmc_toolbox_stub.const import")
    src = src.replace("from .const import", "from bmc_const import")
    src = src.replace("from .logic import", "from bmc_logic import")
    src = src.replace("from .orchestrator import", "from bmc_orchestrator import")
    src = src.replace(
        "from .volume_orchestrator import",
        "from bmc_volume_orchestrator import",
    )
    # Ensure prerequisites are in sys.modules — they're set up by
    # test_module_smoke during collection. Import lazily here:
    import tests.benni_media_context.test_module_smoke  # noqa: F401
    _load_orchestrator_stub()
    _load_volume_orchestrator_stub()
    mod = types.ModuleType("bmc_coord_for_flatten")
    sys.modules["bmc_coord_for_flatten"] = mod
    exec(compile(src, str(MODULE_DIR / "coordinator.py"), "exec"), mod.__dict__)
    return mod


coord_module = _load_coordinator()


# ---------------------------------------------------------------------------
# _flatten_entities
# ---------------------------------------------------------------------------


def test_flatten_handles_none_and_empty():
    f = coord_module._flatten_entities
    assert f(None) == []
    assert f("") == []
    assert f([]) == []
    assert f(()) == []
    assert f(set()) == []


def test_flatten_handles_single_string():
    assert coord_module._flatten_entities("media_player.homepod") == ["media_player.homepod"]


def test_flatten_handles_list_of_strings_preserving_order():
    out = coord_module._flatten_entities([
        "media_player.a", "media_player.b", "media_player.a", "",
    ])
    assert out == ["media_player.a", "media_player.b"]


def test_flatten_handles_nested_list_one_level_deep():
    """Old YAML imports occasionally produced a list-of-lists for
    multi-entity slots. We flatten one level so the tracker doesn't
    crash."""
    out = coord_module._flatten_entities([
        ["media_player.a"], "media_player.b", ["media_player.c"],
    ])
    assert out == ["media_player.a", "media_player.b", "media_player.c"]


def test_flatten_drops_none_and_empty_inside_list():
    out = coord_module._flatten_entities([
        None, "media_player.x", "", " ", "media_player.x",
    ])
    assert out == ["media_player.x"]


def test_flatten_trims_whitespace():
    assert coord_module._flatten_entities("  sensor.x  ") == ["sensor.x"]
    assert coord_module._flatten_entities(["  a  ", "b"]) == ["a", "b"]


def test_flatten_accepts_tuple_and_set():
    assert coord_module._flatten_entities(("a", "b", "a")) == ["a", "b"]
    s = coord_module._flatten_entities({"a", "b"})
    assert sorted(s) == ["a", "b"]


# ---------------------------------------------------------------------------
# _first_entity: single-source semantics from a list-shaped legacy value.
# ---------------------------------------------------------------------------


def test_first_entity_collapses_list_to_first_valid_string():
    f = coord_module._first_entity
    assert f(["media_player.homepod_living", "media_player.homepod_office"]) == \
        "media_player.homepod_living"


def test_first_entity_handles_string_value():
    assert coord_module._first_entity("media_player.x") == "media_player.x"


def test_first_entity_returns_none_on_empty():
    assert coord_module._first_entity(None) is None
    assert coord_module._first_entity("") is None
    assert coord_module._first_entity([]) is None
    assert coord_module._first_entity([None, ""]) is None


# ---------------------------------------------------------------------------
# Regression: building a tracker list with mixed shapes no longer
# crashes the dedupe.
# ---------------------------------------------------------------------------


def test_mixed_shapes_dedupe_without_typeerror():
    """The exact failure mode of v0.3.6: a list slipped into the
    tracker list and `dict.fromkeys(entities)` blew up. The new
    flattener accepts the whole mess and yields a flat ordered list."""
    raw = [
        "media_player.lgtv",
        ["media_player.homepod_a", "media_player.homepod_b"],
        None,
        "media_player.lgtv",  # duplicate
        "",
        "media_player.living_denon",
    ]
    out = coord_module._flatten_entities(raw)
    assert out == [
        "media_player.lgtv",
        "media_player.homepod_a",
        "media_player.homepod_b",
        "media_player.living_denon",
    ]
