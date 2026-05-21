"""Suggested object IDs for cover_policy entities.

HA reads `entity._attr_suggested_object_id` when an entity is first
registered. We derive the base slug from the configured cover entity so
fresh setups land on readable IDs like
`sensor.living_blackout_blind_cover_mode`. Existing registry entries
are not touched — HA respects the user's manual renames after first
registration.
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
) / "custom_components" / "bennis_toolbox" / "modules" / "cover_policy"


# ---------------------------------------------------------------------------
# Minimal HA stubs so entities.py can be loaded without homeassistant.
# Idempotent — earlier test files may already have installed pieces.
# ---------------------------------------------------------------------------


def _install_stubs() -> None:
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    ha.__path__ = []  # type: ignore[attr-defined]

    ha_core = sys.modules.setdefault(
        "homeassistant.core", types.ModuleType("homeassistant.core")
    )

    class _HA: ...

    if not hasattr(ha_core, "HomeAssistant"):
        ha_core.HomeAssistant = _HA

    def _cb(fn):
        return fn

    if not hasattr(ha_core, "callback"):
        ha_core.callback = _cb

    ha_const = sys.modules.setdefault(
        "homeassistant.const", types.ModuleType("homeassistant.const")
    )
    if not hasattr(ha_const, "Platform"):
        class _Platform:
            SENSOR = "sensor"
            BINARY_SENSOR = "binary_sensor"
        ha_const.Platform = _Platform

    ha_ce = sys.modules.setdefault(
        "homeassistant.config_entries", types.ModuleType("homeassistant.config_entries")
    )

    class _ConfigEntry:
        def __init__(self, data=None, entry_id="test-entry-id", title="Test"):
            self.data = dict(data or {})
            self.options = {}
            self.entry_id = entry_id
            self.title = title

    if not hasattr(ha_ce, "ConfigEntry"):
        ha_ce.ConfigEntry = _ConfigEntry

    # Sensor / binary_sensor base classes
    ha_components = sys.modules.setdefault(
        "homeassistant.components", types.ModuleType("homeassistant.components")
    )
    ha_components.__path__ = getattr(ha_components, "__path__", [])

    ha_sensor = sys.modules.setdefault(
        "homeassistant.components.sensor", types.ModuleType("homeassistant.components.sensor")
    )

    class _SensorEntity: ...

    if not hasattr(ha_sensor, "SensorEntity"):
        ha_sensor.SensorEntity = _SensorEntity

    ha_bs = sys.modules.setdefault(
        "homeassistant.components.binary_sensor",
        types.ModuleType("homeassistant.components.binary_sensor"),
    )

    class _BinarySensorEntity: ...

    if not hasattr(ha_bs, "BinarySensorEntity"):
        ha_bs.BinarySensorEntity = _BinarySensorEntity

    ha_helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    ha_helpers.__path__ = getattr(ha_helpers, "__path__", [])

    ha_entity = sys.modules.setdefault(
        "homeassistant.helpers.entity", types.ModuleType("homeassistant.helpers.entity")
    )
    if not hasattr(ha_entity, "EntityCategory"):
        class _EntityCategory:
            DIAGNOSTIC = "diagnostic"
        ha_entity.EntityCategory = _EntityCategory


_install_stubs()


# Synthetic toolbox-root + sibling stubs.
if "cp_sid_toolbox_stub" not in sys.modules:
    pkg = types.ModuleType("cp_sid_toolbox_stub")
    pkg.__path__ = []
    sys.modules["cp_sid_toolbox_stub"] = pkg
    const_mod = types.ModuleType("cp_sid_toolbox_stub.const")
    const_mod.DOMAIN = "bennis_toolbox"
    const_mod.DATA_ENTRIES = "entries"

    def _unique_id(module_id: str, *parts: str) -> str:
        return "_".join(("bennis_toolbox", module_id, *parts))

    const_mod.unique_id = _unique_id
    sys.modules["cp_sid_toolbox_stub.const"] = const_mod


# Coordinator stub so entities.py's `from .coordinator import …` resolves.
if "cp_sid_coord_stub" not in sys.modules:
    mod = types.ModuleType("cp_sid_coord_stub")

    class _StubCoord: ...

    mod.CoverPolicyCoordinator = _StubCoord
    mod.coordinator_from_hass = lambda hass, entry_id: None
    sys.modules["cp_sid_coord_stub"] = mod


import cp_const  # noqa: E402  (from cover_policy conftest)


def _load_entities():
    src = (MODULE_DIR / "entities.py").read_text(encoding="utf-8")
    src = src.replace(
        "from ...const import DOMAIN, unique_id",
        "from cp_sid_toolbox_stub.const import DOMAIN, unique_id",
    )
    src = src.replace("from .const import", "from cp_const import")
    src = src.replace("from .coordinator import", "from cp_sid_coord_stub import")
    mod = types.ModuleType("cp_sid_entities")
    sys.modules["cp_sid_entities"] = mod
    exec(compile(src, str(MODULE_DIR / "entities.py"), "exec"), mod.__dict__)
    return mod


entities = _load_entities()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry(cover_entity: str | None = "cover.living_blackout_blind",
           entry_id: str = "abc123") -> object:
    """Build a minimal ConfigEntry-shaped object the entity __init__ accepts."""
    e = types.SimpleNamespace(
        data={"cover_entity": cover_entity} if cover_entity else {},
        options={},
        entry_id=entry_id,
        title="Wohnzimmer Verdunklung",
    )
    return e


class _StubCoord:
    def add_listener(self, *_a, **_kw): pass
    def remove_listener(self, *_a, **_kw): pass


# ---------------------------------------------------------------------------
# 1) Suggested object IDs.
# ---------------------------------------------------------------------------


def test_base_slug_strips_cover_prefix():
    e = _entry("cover.living_blackout_blind")
    assert entities._base_slug(e) == "living_blackout_blind"


def test_base_slug_falls_back_when_cover_missing():
    e = _entry(cover_entity=None, entry_id="abc123")
    # No cover entity → deterministic fallback so HA doesn't generate
    # random suffixes.
    assert entities._base_slug(e) == "cover_policy_abc123"


def test_base_slug_handles_unprefixed_cover_string():
    e = _entry("just_a_slug")
    # Not a real HA entity id but the helper must not crash.
    assert entities._base_slug(e) == "just_a_slug"


def test_mode_sensor_suggested_id_uses_base_slug():
    s = entities.ModeSensor(_StubCoord(), _entry())
    assert s._attr_suggested_object_id == "living_blackout_blind_cover_mode"


def test_target_position_sensor_suggested_id():
    s = entities.TargetPositionSensor(_StubCoord(), _entry())
    assert s._attr_suggested_object_id == "living_blackout_blind_target_position"


def test_reason_sensor_suggested_id():
    s = entities.ReasonSensor(_StubCoord(), _entry())
    assert s._attr_suggested_object_id == "living_blackout_blind_policy_reason"


def test_apply_blocked_binary_sensor_suggested_id():
    s = entities.ApplyBlockedBinarySensor(_StubCoord(), _entry())
    assert s._attr_suggested_object_id == "living_blackout_blind_apply_blocked"


def test_debug_sensor_suggested_id():
    s = entities.DebugSensor(_StubCoord(), _entry())
    assert s._attr_suggested_object_id == "living_blackout_blind_policy_debug"


# ---------------------------------------------------------------------------
# 2) Unique IDs remain stable (entry_id + UID_*, no cover-derived noise).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls,uid",
    [
        ("ModeSensor", "mode"),
        ("TargetPositionSensor", "target_position"),
        ("ReasonSensor", "policy_reason"),
        ("ApplyBlockedBinarySensor", "apply_blocked"),
        ("DebugSensor", "debug"),
    ],
)
def test_unique_id_pattern_unchanged(cls, uid):
    entity = getattr(entities, cls)(_StubCoord(), _entry())
    assert entity._attr_unique_id == f"bennis_toolbox_cover_policy_abc123_{uid}"


def test_unique_id_does_not_depend_on_cover_entity():
    """Changing the cover entity must not break the entity registry —
    unique_id stays tied to entry_id, only suggested_object_id reflects
    the cover slug.
    """
    e1 = _entry("cover.living_blackout_blind", entry_id="abc123")
    e2 = _entry("cover.bedroom_blind", entry_id="abc123")
    a = entities.ModeSensor(_StubCoord(), e1)
    b = entities.ModeSensor(_StubCoord(), e2)
    assert a._attr_unique_id == b._attr_unique_id
    # Suggested object id, on the other hand, reflects the swap.
    assert a._attr_suggested_object_id == "living_blackout_blind_cover_mode"
    assert b._attr_suggested_object_id == "bedroom_blind_cover_mode"
