"""Service-Handler des Wake-Planner-Moduls.

Registriert über die Umbrella unter `bennis_toolbox.wake_planner_<action>`.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...services import ServiceDef
from .const import (
    CONF_HOLIDAY_BEHAVIOR,
    CONF_MANUAL_HOLIDAY_DATES,
    SERVICE_ADD_PERSON,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_REMOVE_PERSON,
    SERVICE_SET_OVERRIDE,
    SERVICE_SET_RULES,
    SERVICE_SET_SPECIAL_RULES,
    SERVICE_SKIP_NEXT,
)
from .coordinator import (
    all_wake_planner_coordinators,
    coordinator_for_person,
    coordinator_from_hass,
)
from .rule_engine import parse_time

PERSON_SCHEMA = vol.Schema({vol.Required("person_id"): cv.string})


def _time_string(value: str) -> str:
    parse_time(value)
    return value


def _require_person_coord(hass, person_id: str):
    coord = coordinator_for_person(hass, person_id)
    if coord is None:
        raise ValueError(f"Unknown Wake Planner person_id: {person_id}")
    return coord


def _any_coord(hass, entry_id: str | None = None):
    if entry_id:
        coord = coordinator_from_hass(hass, entry_id)
        if coord is not None:
            return coord
    coords = all_wake_planner_coordinators(hass)
    if not coords:
        raise ValueError("No Wake Planner config entry loaded")
    return coords[0]


async def _skip_next(hass: HomeAssistant, call: ServiceCall) -> None:
    coord = _require_person_coord(hass, call.data["person_id"])
    await coord.async_skip_next(call.data["person_id"])


async def _set_override(hass: HomeAssistant, call: ServiceCall) -> None:
    coord = _require_person_coord(hass, call.data["person_id"])
    await coord.async_set_override(call.data["person_id"], call.data["wake_time"], call.data.get("until"))


async def _clear_override(hass: HomeAssistant, call: ServiceCall) -> None:
    coord = _require_person_coord(hass, call.data["person_id"])
    await coord.async_clear_override(call.data["person_id"])


async def _add_person(hass: HomeAssistant, call: ServiceCall) -> None:
    coord = _any_coord(hass, call.data.get("entry_id"))
    await coord.async_add_person(call.data["name"], call.data.get("person_entity_id"))


async def _remove_person(hass: HomeAssistant, call: ServiceCall) -> None:
    coord = _require_person_coord(hass, call.data["person_id"])
    await coord.async_remove_person(call.data["person_id"])


async def _set_rules(hass: HomeAssistant, call: ServiceCall) -> None:
    coord = _require_person_coord(hass, call.data["person_id"])
    await coord.async_set_rules(call.data["person_id"], list(call.data["rules"]))


async def _set_special_rules(hass: HomeAssistant, call: ServiceCall) -> None:
    coord = _any_coord(hass)
    updates: dict[str, Any] = {}
    if "holiday_behavior" in call.data:
        updates[CONF_HOLIDAY_BEHAVIOR] = call.data["holiday_behavior"]
    if "manual_holiday_dates" in call.data:
        updates[CONF_MANUAL_HOLIDAY_DATES] = str(call.data.get("manual_holiday_dates", ""))
    if updates:
        await coord.async_update_global_config(**updates)


SERVICES: dict[str, ServiceDef] = {
    SERVICE_SKIP_NEXT: ServiceDef(handler=_skip_next, schema=PERSON_SCHEMA),
    SERVICE_SET_OVERRIDE: ServiceDef(
        handler=_set_override,
        schema=vol.Schema({
            vol.Required("person_id"): cv.string,
            vol.Required("wake_time"): _time_string,
            vol.Optional("until"): cv.date,
        }),
    ),
    SERVICE_CLEAR_OVERRIDE: ServiceDef(handler=_clear_override, schema=PERSON_SCHEMA),
    SERVICE_ADD_PERSON: ServiceDef(
        handler=_add_person,
        schema=vol.Schema({
            vol.Required("name"): cv.string,
            vol.Optional("person_entity_id"): cv.string,
            vol.Optional("entry_id"): cv.string,
        }),
    ),
    SERVICE_REMOVE_PERSON: ServiceDef(handler=_remove_person, schema=PERSON_SCHEMA),
    SERVICE_SET_RULES: ServiceDef(
        handler=_set_rules,
        schema=vol.Schema({
            vol.Required("person_id"): cv.string,
            vol.Required("rules"): list,
        }),
    ),
    SERVICE_SET_SPECIAL_RULES: ServiceDef(
        handler=_set_special_rules,
        schema=vol.Schema({
            vol.Optional("holiday_behavior"): cv.string,
            vol.Optional("manual_holiday_dates"): cv.string,
        }),
    ),
}
