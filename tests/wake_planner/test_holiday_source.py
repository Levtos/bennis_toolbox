"""Unit tests for Wake Planner holiday event detection."""

from __future__ import annotations

from datetime import date, datetime
import importlib.util
import asyncio
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = ROOT / "custom_components" / "bennis_toolbox" / "modules" / "wake_planner"

ha_mod = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
core_mod = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))
if not hasattr(core_mod, "HomeAssistant"):
    core_mod.HomeAssistant = object


# Build a synthetic package so holiday_source's `from .calendar_cache import …`
# resolves to a sibling module within the test sandbox.
_pkg_name = "wp_hol_pkg"
_pkg = sys.modules.get(_pkg_name)
if _pkg is None:
    _pkg = types.ModuleType(_pkg_name)
    _pkg.__path__ = [str(MODULE_DIR)]
    sys.modules[_pkg_name] = _pkg
    for fname, alias in (
        ("calendar_cache.py", f"{_pkg_name}.calendar_cache"),
        ("holiday_source.py", f"{_pkg_name}.holiday_source"),
    ):
        spec = importlib.util.spec_from_file_location(alias, MODULE_DIR / fname)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[alias] = mod
        spec.loader.exec_module(mod)

holiday_source = sys.modules[f"{_pkg_name}.holiday_source"]
calendar_cache = sys.modules[f"{_pkg_name}.calendar_cache"]
CalendarCache = calendar_cache.CalendarCache


@pytest.mark.parametrize(
    "event",
    [
        {"all_day": True, "start": "2026-05-25T00:00:00+02:00"},
        {"start": "2026-05-25"},
        {"start_time": "2026-05-25"},
        {"date": "2026-05-25"},
        {"start": {"date": "2026-05-25"}},
    ],
)
def test_all_day_event_shapes_are_detected(event):
    assert holiday_source._is_all_day_event(event)


@pytest.mark.parametrize(
    "event",
    [
        {"all_day": False, "start": "2026-05-25T09:00:00+02:00"},
        {"start": {"dateTime": "2026-05-25T09:00:00+02:00"}},
        {"start": "2026-05-25T09:00:00"},
        {},
    ],
)
def test_timed_event_shapes_are_not_holidays(event):
    assert not holiday_source._is_all_day_event(event)


def test_holiday_map_uses_date_only_calendar_events():
    class _Services:
        async def async_call(self, _domain, _service, data, **_kwargs):
            return {"calendar.feiertage": {"events": [
                {"start": {"date": "2026-05-25"}, "summary": "Pfingstmontag"},
            ]}}

    class _States:
        def get(self, _entity_id):
            return type("State", (), {"state": "on"})()

    class _Hass:
        services = _Services()
        states = _States()

    cache = CalendarCache(_Hass(), min_refresh_interval=0)
    holidays = asyncio.run(
        holiday_source.async_holiday_map(
            _Hass(),
            "calendar.feiertage",
            date(2026, 5, 24),
            date(2026, 5, 26),
            None,
            cache=cache,
        )
    )

    assert holidays[date(2026, 5, 25)] == (True, "Pfingstmontag")


def test_holiday_map_skips_unavailable_calendar_without_service_call():
    class _Services:
        async def async_call(self, *_args, **_kwargs):
            raise AssertionError("calendar.get_events should not be called")

    class _States:
        def get(self, _entity_id):
            return type("State", (), {"state": "unavailable"})()

    class _Hass:
        services = _Services()
        states = _States()

    cache = CalendarCache(_Hass(), min_refresh_interval=0)
    holidays = asyncio.run(
        holiday_source.async_holiday_map(
            _Hass(),
            "calendar.feiertage",
            date(2026, 5, 25),
            date(2026, 5, 25),
            None,
            cache=cache,
        )
    )

    # 2026-05-25 is a Monday; without a working calendar and no weekend,
    # there should be no holiday entries at all.
    assert holidays == {}
