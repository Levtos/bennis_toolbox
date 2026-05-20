"""Services for Wake Planner."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_HOLIDAY_BEHAVIOR,
    CONF_MANUAL_HOLIDAY_DATES,
    DOMAIN,
    SERVICE_ADD_PERSON,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_REMOVE_PERSON,
    SERVICE_SET_OVERRIDE,
    SERVICE_SET_RULES,
    SERVICE_SET_SPECIAL_RULES,
    SERVICE_SKIP_NEXT,
)
from .coordinator import WakePlannerCoordinator
from .rule_engine import parse_time

PERSON_SCHEMA = vol.Schema({vol.Required("person_id"): cv.string})


def _time_string(value: str) -> str:
    parse_time(value)
    return value


def _first_coordinator(hass: HomeAssistant) -> WakePlannerCoordinator:
    coordinators = list(hass.data.get(DOMAIN, {}).values())
    if not coordinators:
        raise ValueError("No Wake Planner config entry loaded")
    return coordinators[0]


def _coordinator_for_person(hass: HomeAssistant, person_id: str) -> WakePlannerCoordinator:
    for coordinator in hass.data.get(DOMAIN, {}).values():
        if person_id in {person.slug for person in coordinator.persons}:
            return coordinator
    raise ValueError(f"Unknown Wake Planner person_id: {person_id}")


def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SKIP_NEXT):
        return

    async def skip_next(call: ServiceCall) -> None:
        coordinator = _coordinator_for_person(hass, call.data["person_id"])
        await coordinator.async_skip_next(call.data["person_id"])

    async def set_override(call: ServiceCall) -> None:
        coordinator = _coordinator_for_person(hass, call.data["person_id"])
        await coordinator.async_set_override(
            call.data["person_id"], call.data["wake_time"], call.data.get("until")
        )

    async def clear_override(call: ServiceCall) -> None:
        coordinator = _coordinator_for_person(hass, call.data["person_id"])
        await coordinator.async_clear_override(call.data["person_id"])

    async def add_person(call: ServiceCall) -> None:
        target = call.data.get("entry_id")
        coordinator = None
        if target:
            coordinator = hass.data.get(DOMAIN, {}).get(target)
        if coordinator is None:
            coordinator = _first_coordinator(hass)
        await coordinator.async_add_person(
            call.data["name"], call.data.get("person_entity_id")
        )

    async def remove_person(call: ServiceCall) -> None:
        coordinator = _coordinator_for_person(hass, call.data["person_id"])
        await coordinator.async_remove_person(call.data["person_id"])

    async def set_rules(call: ServiceCall) -> None:
        coordinator = _coordinator_for_person(hass, call.data["person_id"])
        await coordinator.async_set_rules(call.data["person_id"], list(call.data["rules"]))

    async def set_special_rules(call: ServiceCall) -> None:
        coordinator = _first_coordinator(hass)
        updates: dict[str, Any] = {}
        if "holiday_behavior" in call.data:
            updates[CONF_HOLIDAY_BEHAVIOR] = call.data["holiday_behavior"]
        if "manual_holiday_dates" in call.data:
            updates[CONF_MANUAL_HOLIDAY_DATES] = str(call.data.get("manual_holiday_dates", ""))
        if updates:
            await coordinator.async_update_global_config(**updates)

    hass.services.async_register(DOMAIN, SERVICE_SKIP_NEXT, skip_next, schema=PERSON_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_OVERRIDE, set_override,
        schema=vol.Schema({
            vol.Required("person_id"): cv.string,
            vol.Required("wake_time"): _time_string,
            vol.Optional("until"): cv.date,
        }),
    )
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_OVERRIDE, clear_override, schema=PERSON_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_PERSON, add_person,
        schema=vol.Schema({
            vol.Required("name"): cv.string,
            vol.Optional("person_entity_id"): cv.string,
            vol.Optional("entry_id"): cv.string,
        }),
    )
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_PERSON, remove_person, schema=PERSON_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_RULES, set_rules,
        schema=vol.Schema({
            vol.Required("person_id"): cv.string,
            vol.Required("rules"): list,
        }),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SPECIAL_RULES, set_special_rules,
        schema=vol.Schema({
            vol.Optional("holiday_behavior"): cv.string,
            vol.Optional("manual_holiday_dates"): cv.string,
        }),
    )
