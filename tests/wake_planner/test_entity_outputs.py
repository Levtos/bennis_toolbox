"""Wake Planner entity outputs for benni_context consumption.

Pin two contracts so downstream `benni_context` can rely on them:

1. ``suggested_object_id`` produces readable, semantically clear entity
   ids — `binary_sensor.wake_planner_<slug>_wake_needed` and
   `sensor.wake_planner_<slug>_next_wake`, not HA's German
   device-class fallback (`…_betriebszustand`, `…_zeitstempel`).
2. The wake-needed binary sensor's truth table:
   - state SCHEDULED inside the wake window → on
   - state SCHEDULED outside the window → off
   - state SKIPPED / HOLIDAY / INACTIVE → off (regardless of window)
   - state OVERRIDDEN inside the window → on
   - missing window timestamps → off

Loads entities.py with minimal HA stubs so we can hold the contract
without pulling in homeassistant proper.
"""
from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


MODULE_DIR = Path(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
) / "custom_components" / "bennis_toolbox" / "modules" / "wake_planner"


# ---------------------------------------------------------------------------
# HA stubs.
# ---------------------------------------------------------------------------


_NOW: datetime | None = None


def _install_ha_stubs() -> None:
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    ha.__path__ = []  # type: ignore[attr-defined]

    ha_core = sys.modules.setdefault(
        "homeassistant.core", types.ModuleType("homeassistant.core")
    )

    class _HA: ...

    def _cb(fn):
        return fn

    for attr, value in (("HomeAssistant", _HA), ("callback", _cb), ("Event", object)):
        if not hasattr(ha_core, attr):
            setattr(ha_core, attr, value)

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
        def __init__(self, data=None, options=None, entry_id="wp-entry"):
            self.data = data or {}
            self.options = options or {}
            self.entry_id = entry_id

    if not hasattr(ha_ce, "ConfigEntry"):
        ha_ce.ConfigEntry = _ConfigEntry

    ha_components = sys.modules.setdefault(
        "homeassistant.components", types.ModuleType("homeassistant.components")
    )
    ha_components.__path__ = getattr(ha_components, "__path__", [])

    ha_sensor = sys.modules.setdefault(
        "homeassistant.components.sensor", types.ModuleType("homeassistant.components.sensor")
    )

    class _SensorEntity: ...

    @dataclass
    class _SensorEntityDescription:
        key: str
        translation_key: str | None = None
        device_class: str | None = None
        options: list | None = None

    class _SensorDeviceClass:
        TIMESTAMP = "timestamp"
        ENUM = "enum"

    if not hasattr(ha_sensor, "SensorEntity"):
        ha_sensor.SensorEntity = _SensorEntity
    if not hasattr(ha_sensor, "SensorEntityDescription"):
        ha_sensor.SensorEntityDescription = _SensorEntityDescription
    if not hasattr(ha_sensor, "SensorDeviceClass"):
        ha_sensor.SensorDeviceClass = _SensorDeviceClass

    ha_bs = sys.modules.setdefault(
        "homeassistant.components.binary_sensor",
        types.ModuleType("homeassistant.components.binary_sensor"),
    )

    class _BinarySensorEntity: ...

    @dataclass
    class _BinarySensorEntityDescription:
        key: str
        translation_key: str | None = None
        device_class: str | None = None

    class _BinarySensorDeviceClass:
        RUNNING = "running"

    if not hasattr(ha_bs, "BinarySensorEntity"):
        ha_bs.BinarySensorEntity = _BinarySensorEntity
    if not hasattr(ha_bs, "BinarySensorEntityDescription"):
        ha_bs.BinarySensorEntityDescription = _BinarySensorEntityDescription
    if not hasattr(ha_bs, "BinarySensorDeviceClass"):
        ha_bs.BinarySensorDeviceClass = _BinarySensorDeviceClass

    ha_helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    ha_helpers.__path__ = getattr(ha_helpers, "__path__", [])

    ha_uc = sys.modules.setdefault(
        "homeassistant.helpers.update_coordinator",
        types.ModuleType("homeassistant.helpers.update_coordinator"),
    )

    class _CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

        def __class_getitem__(cls, item):
            return cls

    if not hasattr(ha_uc, "CoordinatorEntity"):
        ha_uc.CoordinatorEntity = _CoordinatorEntity

    ha_util = sys.modules.setdefault(
        "homeassistant.util", types.ModuleType("homeassistant.util")
    )
    ha_util.__path__ = getattr(ha_util, "__path__", [])

    ha_dt = sys.modules.setdefault(
        "homeassistant.util.dt", types.ModuleType("homeassistant.util.dt")
    )
    ha_dt.UTC = timezone.utc

    def _now():
        return _NOW if _NOW is not None else datetime.now(timezone.utc)

    def _as_local(dt: datetime) -> datetime:
        # For the test we keep everything in UTC; this is enough to
        # exercise the window comparison without HA's zoneinfo dance.
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    ha_dt.now = _now
    ha_dt.as_local = _as_local
    ha_dt.utcnow = lambda: datetime.now(timezone.utc)


_install_ha_stubs()


# ---------------------------------------------------------------------------
# Synthetic toolbox stubs so entities.py's relative imports resolve.
# ---------------------------------------------------------------------------


if "wp_tb_stub" not in sys.modules:
    pkg = types.ModuleType("wp_tb_stub")
    pkg.__path__ = []
    sys.modules["wp_tb_stub"] = pkg
    const_mod = types.ModuleType("wp_tb_stub.const")
    const_mod.DOMAIN = "bennis_toolbox"

    def _unique_id(module_id: str, *parts: str) -> str:
        return "_".join(("bennis_toolbox", module_id, *parts))

    const_mod.unique_id = _unique_id
    sys.modules["wp_tb_stub.const"] = const_mod


# Reuse the HA-free const/rule_engine that the wake_planner conftest
# already loaded; expose them as `wp_const` / `wp_rule_engine` for the
# rewritten entities.py source.
import wp_const  # noqa: E402  (loaded by tests/wake_planner/conftest.py)


# Util shim — entities.py imports `from .util import rule_to_dict`.
if "wp_util_stub" not in sys.modules:
    mod = types.ModuleType("wp_util_stub")

    def rule_to_dict(r):
        return {"name": getattr(r, "name", "<rule>")}

    mod.rule_to_dict = rule_to_dict
    sys.modules["wp_util_stub"] = mod


if "wp_coord_stub" not in sys.modules:
    mod = types.ModuleType("wp_coord_stub")

    class _WPC: ...

    mod.WakePlannerCoordinator = _WPC
    mod.coordinator_from_hass = lambda hass, entry_id: None
    sys.modules["wp_coord_stub"] = mod


def _load_entities():
    src = (MODULE_DIR / "entities.py").read_text(encoding="utf-8")
    src = src.replace("from ...const import", "from wp_tb_stub.const import")
    src = src.replace("from .const import", "from wp_const import")
    src = src.replace("from .util import", "from wp_util_stub import")
    src = src.replace("from .coordinator import", "from wp_coord_stub import")
    mod = types.ModuleType("wp_entities_under_test")
    sys.modules["wp_entities_under_test"] = mod
    exec(compile(src, str(MODULE_DIR / "entities.py"), "exec"), mod.__dict__)
    return mod


entities = _load_entities()


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


@dataclass
class _Person:
    slug: str
    name: str
    wake_window_minutes: int = 10
    rules: list = field(default_factory=list)


def _entry():
    return types.SimpleNamespace(data={}, options={}, entry_id="entry-1")


@dataclass
class _StubDecision:
    state: object
    wake_window_start: datetime | None = None
    wake_window_end: datetime | None = None
    wake_time: str | None = None
    decided_by: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "state": getattr(self.state, "value", str(self.state)),
            "wake_window_start": self.wake_window_start.isoformat() if self.wake_window_start else None,
            "wake_window_end": self.wake_window_end.isoformat() if self.wake_window_end else None,
            "wake_time": self.wake_time,
            "decided_by": self.decided_by,
            "reason": self.reason,
        }


class _StubCoord:
    def __init__(self, decision=None, next_wake=None):
        slug = "benni"
        self.data = {slug: decision} if decision else {}
        self.next_wakes = {slug: next_wake} if next_wake else {}
        self.persons = [_Person(slug=slug, name="Benni")]
        self.options = {}


def _set_now(dt: datetime) -> None:
    """Pin `dt_util.now()` for the binary-sensor truth-table tests."""
    import homeassistant.util.dt as ha_dt
    globals_ns = sys.modules[__name__].__dict__
    globals_ns["_NOW"] = dt
    # The stub picks up `_NOW` from this test module's namespace via the
    # `_now` closure created in `_install_ha_stubs`; we patch the
    # closure's read by mutating the module-level name there too.
    ha_dt_now_module = ha_dt
    ha_dt_now_module.__dict__["_NOW"] = dt
    # Simpler: replace the function with one that returns dt.
    ha_dt_now_module.now = lambda dt=dt: dt


# ---------------------------------------------------------------------------
# 1) suggested_object_id contract.
# ---------------------------------------------------------------------------


def test_next_wake_sensor_has_readable_suggested_object_id():
    coord = _StubCoord()
    entry = _entry()
    desc = entities.SENSOR_DESCRIPTIONS[1]  # next_wake
    sensor = entities.WakePlannerSensor(coord, entry, coord.persons[0], desc)
    assert sensor._attr_suggested_object_id == "wake_planner_benni_next_wake"


def test_wake_state_sensor_has_readable_suggested_object_id():
    coord = _StubCoord()
    entry = _entry()
    desc = entities.SENSOR_DESCRIPTIONS[0]  # wake_state
    sensor = entities.WakePlannerSensor(coord, entry, coord.persons[0], desc)
    assert sensor._attr_suggested_object_id == "wake_planner_benni_wake_state"


def test_wake_needed_binary_sensor_has_readable_suggested_object_id():
    coord = _StubCoord()
    entry = _entry()
    binary = entities.WakeNeededBinarySensor(coord, entry, coord.persons[0])
    assert binary._attr_suggested_object_id == "wake_planner_benni_wake_needed"


def test_unique_ids_unchanged():
    """unique_id is what HA uses to keep registry identity stable.
    These three patterns must remain unchanged across the suggested-
    object-id work."""
    coord = _StubCoord()
    entry = _entry()
    next_wake = entities.WakePlannerSensor(coord, entry, coord.persons[0], entities.SENSOR_DESCRIPTIONS[1])
    wake_state = entities.WakePlannerSensor(coord, entry, coord.persons[0], entities.SENSOR_DESCRIPTIONS[0])
    wake_needed = entities.WakeNeededBinarySensor(coord, entry, coord.persons[0])
    assert next_wake._attr_unique_id == "bennis_toolbox_wake_planner_entry-1_benni_next_wake"
    assert wake_state._attr_unique_id == "bennis_toolbox_wake_planner_entry-1_benni_wake_state"
    assert wake_needed._attr_unique_id == "bennis_toolbox_wake_planner_entry-1_benni_wake_needed"


# ---------------------------------------------------------------------------
# 2) wake-needed binary sensor truth table.
# ---------------------------------------------------------------------------


@pytest.fixture
def _entry_object():
    return _entry()


def _window(now: datetime) -> tuple[datetime, datetime]:
    """A 10-minute window centred on `now`."""
    return (now - timedelta(minutes=5), now + timedelta(minutes=5))


def test_wake_needed_on_when_scheduled_and_inside_window(_entry_object):
    now = datetime(2026, 5, 22, 7, 0, tzinfo=timezone.utc)
    _set_now(now)
    start, end = _window(now)
    decision = _StubDecision(state=wp_const.WakeState.SCHEDULED, wake_window_start=start, wake_window_end=end)
    coord = _StubCoord(decision=decision)
    binary = entities.WakeNeededBinarySensor(coord, _entry_object, coord.persons[0])
    assert binary.is_on is True


def test_wake_needed_off_when_scheduled_but_outside_window(_entry_object):
    now = datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc)  # past the window
    _set_now(now)
    start = datetime(2026, 5, 22, 6, 55, tzinfo=timezone.utc)
    end = datetime(2026, 5, 22, 7, 5, tzinfo=timezone.utc)
    decision = _StubDecision(state=wp_const.WakeState.SCHEDULED, wake_window_start=start, wake_window_end=end)
    coord = _StubCoord(decision=decision)
    binary = entities.WakeNeededBinarySensor(coord, _entry_object, coord.persons[0])
    assert binary.is_on is False


def test_wake_needed_on_when_overridden_inside_window(_entry_object):
    now = datetime(2026, 5, 22, 7, 0, tzinfo=timezone.utc)
    _set_now(now)
    start, end = _window(now)
    decision = _StubDecision(state=wp_const.WakeState.OVERRIDDEN, wake_window_start=start, wake_window_end=end)
    coord = _StubCoord(decision=decision)
    binary = entities.WakeNeededBinarySensor(coord, _entry_object, coord.persons[0])
    assert binary.is_on is True


@pytest.mark.parametrize("state_attr", ["SKIPPED", "HOLIDAY", "INACTIVE"])
def test_wake_needed_off_for_non_wakeable_states(_entry_object, state_attr):
    now = datetime(2026, 5, 22, 7, 0, tzinfo=timezone.utc)
    _set_now(now)
    start, end = _window(now)
    state = getattr(wp_const.WakeState, state_attr)
    decision = _StubDecision(state=state, wake_window_start=start, wake_window_end=end)
    coord = _StubCoord(decision=decision)
    binary = entities.WakeNeededBinarySensor(coord, _entry_object, coord.persons[0])
    assert binary.is_on is False, state_attr


def test_wake_needed_off_when_window_missing(_entry_object):
    decision = _StubDecision(state=wp_const.WakeState.SCHEDULED)
    coord = _StubCoord(decision=decision)
    binary = entities.WakeNeededBinarySensor(coord, _entry_object, coord.persons[0])
    assert binary.is_on is False


def test_wake_needed_off_when_no_decision(_entry_object):
    coord = _StubCoord(decision=None)
    binary = entities.WakeNeededBinarySensor(coord, _entry_object, coord.persons[0])
    assert binary.is_on is False


# ---------------------------------------------------------------------------
# 3) next_wake sensor stays timezone-aware and ISO-stable.
# ---------------------------------------------------------------------------


def test_next_wake_sensor_returns_aware_timestamp_value(_entry_object):
    coord = _StubCoord(
        decision=_StubDecision(state=wp_const.WakeState.SCHEDULED),
        next_wake=datetime(2026, 5, 23, 7, 0, tzinfo=timezone.utc),
    )
    sensor = entities.WakePlannerSensor(coord, _entry_object, coord.persons[0], entities.SENSOR_DESCRIPTIONS[1])
    val = sensor.native_value
    assert isinstance(val, datetime)
    assert val.tzinfo is not None
    # ISO formatting includes the offset → benni_context can consume it
    # as a stable, timezone-safe timestamp.
    assert val.isoformat() == "2026-05-23T07:00:00+00:00"


def test_next_wake_sensor_uses_timestamp_device_class():
    desc = entities.SENSOR_DESCRIPTIONS[1]
    assert desc.key == "next_wake"
    assert desc.device_class == "timestamp"


def test_wake_needed_uses_running_device_class():
    desc = entities.BINARY_DESCRIPTION
    assert desc.key == "wake_needed"
    assert desc.device_class == "running"


# ---------------------------------------------------------------------------
# 4) wake_state sensor: ENUM device-class + options so HA validation
#    actually accepts the value instead of falling back to "unknown".
# ---------------------------------------------------------------------------


def test_wake_state_sensor_declares_enum_device_class_with_options():
    """Regression for 0.3.5.4 bug: after the umbrella translations
    started shipping `entity.sensor.wake_state.state.*`, HA validated
    the value against `options`. Without options declared the entity
    silently became `unknown` even though the WakeDecision was correct.
    """
    desc = entities.SENSOR_DESCRIPTIONS[0]
    assert desc.key == "wake_state"
    assert desc.device_class == "enum"
    expected = {"scheduled", "skipped", "overridden", "holiday", "inactive"}
    assert set(desc.options) == expected


@pytest.mark.parametrize(
    "state_attr,expected_value",
    [
        ("SCHEDULED", "scheduled"),
        ("SKIPPED", "skipped"),
        ("OVERRIDDEN", "overridden"),
        ("HOLIDAY", "holiday"),
        ("INACTIVE", "inactive"),
    ],
)
def test_wake_state_native_value_is_concrete_string_when_decision_present(
    _entry_object, state_attr, expected_value,
):
    state = getattr(wp_const.WakeState, state_attr)
    decision = _StubDecision(state=state)
    coord = _StubCoord(decision=decision)
    sensor = entities.WakePlannerSensor(
        coord, _entry_object, coord.persons[0], entities.SENSOR_DESCRIPTIONS[0],
    )
    val = sensor.native_value
    assert val == expected_value
    # Every value must be in the declared options — that's HA's
    # acceptance criterion for ENUM sensors.
    assert val in entities.SENSOR_DESCRIPTIONS[0].options


def test_wake_state_native_value_none_only_when_no_decision(_entry_object):
    """If the coordinator hasn't produced a decision yet (cold start),
    native_value falls back to None which HA renders as `unknown` —
    that's expected. The bug we're guarding is the "decision exists
    but sensor still shows unknown" case above."""
    coord = _StubCoord(decision=None)
    sensor = entities.WakePlannerSensor(
        coord, _entry_object, coord.persons[0], entities.SENSOR_DESCRIPTIONS[0],
    )
    assert sensor.native_value is None
