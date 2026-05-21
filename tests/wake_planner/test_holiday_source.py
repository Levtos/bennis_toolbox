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

ha_mod = types.ModuleType("homeassistant")
core_mod = types.ModuleType("homeassistant.core")
core_mod.HomeAssistant = object
sys.modules.setdefault("homeassistant", ha_mod)
sys.modules.setdefault("homeassistant.core", core_mod)

spec = importlib.util.spec_from_file_location("wp_holiday_source", MODULE_DIR / "holiday_source.py")
holiday_source = importlib.util.module_from_spec(spec)
sys.modules["wp_holiday_source"] = holiday_source
spec.loader.exec_module(holiday_source)


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
            day = datetime.fromisoformat(data["start_date_time"]).date()
            events = []
            if day == date(2026, 5, 25):
                events.append({"start": {"date": "2026-05-25"}, "summary": "Pfingstmontag"})
            return {"calendar.feiertage": {"events": events}}

    class _States:
        def get(self, _entity_id):
            return type("State", (), {"state": "on"})()

    class _Hass:
        services = _Services()
        states = _States()

    holidays = asyncio.run(
        holiday_source.async_holiday_map(
            _Hass(),
            "calendar.feiertage",
            date(2026, 5, 24),
            date(2026, 5, 26),
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

    holidays = asyncio.run(
        holiday_source.async_holiday_map(
            _Hass(),
            "calendar.feiertage",
            date(2026, 5, 25),
            date(2026, 5, 25),
        )
    )

    assert holidays == {}
