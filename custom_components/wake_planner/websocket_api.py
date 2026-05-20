"""WebSocket API for the Wake Planner panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_HOLIDAY_BEHAVIOR,
    CONF_MANUAL_HOLIDAY_DATES,
    DOMAIN,
    HOLIDAY_SKIP,
)
from .coordinator import WakePlannerCoordinator


def _first_coordinator(hass: HomeAssistant) -> WakePlannerCoordinator | None:
    items = list(hass.data.get(DOMAIN, {}).values())
    return items[0] if items else None


def _coordinator_for_person(hass: HomeAssistant, person_id: str) -> WakePlannerCoordinator | None:
    for coordinator in hass.data.get(DOMAIN, {}).values():
        if person_id in {person.slug for person in coordinator.persons}:
            return coordinator
    return None


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register all wake_planner/* WebSocket commands once."""
    if hass.data.get(f"{DOMAIN}_ws_registered"):
        return
    hass.data[f"{DOMAIN}_ws_registered"] = True

    websocket_api.async_register_command(hass, ws_get_state)
    websocket_api.async_register_command(hass, ws_get_schedule)
    websocket_api.async_register_command(hass, ws_add_person)
    websocket_api.async_register_command(hass, ws_remove_person)
    websocket_api.async_register_command(hass, ws_update_person)
    websocket_api.async_register_command(hass, ws_set_rules)
    websocket_api.async_register_command(hass, ws_set_global)
    websocket_api.async_register_command(hass, ws_skip_next)
    websocket_api.async_register_command(hass, ws_set_override)
    websocket_api.async_register_command(hass, ws_clear_override)


def _serialise_state(coordinator: WakePlannerCoordinator) -> dict[str, Any]:
    opts = coordinator.options
    return {
        "entry_id": coordinator.entry.entry_id,
        "persons": [coordinator.serialize_person(p) for p in coordinator.persons],
        "global": {
            "holiday_behavior": opts.get(CONF_HOLIDAY_BEHAVIOR, HOLIDAY_SKIP),
            "manual_holiday_dates": opts.get(CONF_MANUAL_HOLIDAY_DATES, ""),
            "calendar_entity_id": opts.get("calendar_entity_id"),
            "holiday_calendar_entity_id": opts.get("holiday_calendar_entity_id"),
        },
    }


@websocket_api.websocket_command({vol.Required("type"): "wake_planner/get_state"})
@websocket_api.async_response
async def ws_get_state(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    coordinator = _first_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_loaded", "Wake Planner not configured")
        return
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): "wake_planner/get_schedule",
    vol.Optional("days", default=14): vol.All(int, vol.Range(min=1, max=60)),
})
@websocket_api.async_response
async def ws_get_schedule(hass, connection, msg):
    coordinator = _first_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_loaded", "Wake Planner not configured")
        return
    schedule = await coordinator.async_get_schedule(msg.get("days", 14))
    connection.send_result(msg["id"], {"schedule": schedule})


@websocket_api.websocket_command({
    vol.Required("type"): "wake_planner/add_person",
    vol.Required("name"): str,
    vol.Optional("person_entity_id"): vol.Any(str, None),
})
@websocket_api.async_response
async def ws_add_person(hass, connection, msg):
    coordinator = _first_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_loaded", "Wake Planner not configured")
        return
    slug = await coordinator.async_add_person(msg["name"], msg.get("person_entity_id"))
    connection.send_result(msg["id"], {"slug": slug, **_serialise_state(coordinator)})


@websocket_api.websocket_command({
    vol.Required("type"): "wake_planner/remove_person",
    vol.Required("person_id"): str,
})
@websocket_api.async_response
async def ws_remove_person(hass, connection, msg):
    coordinator = _coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    await coordinator.async_remove_person(msg["person_id"])
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): "wake_planner/update_person",
    vol.Required("person_id"): str,
    vol.Optional("name"): str,
    vol.Optional("person_entity_id"): vol.Any(str, None),
    vol.Optional("wake_window_minutes"): vol.All(int, vol.Range(min=1, max=120)),
})
@websocket_api.async_response
async def ws_update_person(hass, connection, msg):
    coordinator = _coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    updates = {k: v for k, v in msg.items() if k in {"name", "person_entity_id", "wake_window_minutes"}}
    if updates:
        await coordinator.async_update_person(msg["person_id"], **updates)
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): "wake_planner/set_rules",
    vol.Required("person_id"): str,
    vol.Required("rules"): list,
})
@websocket_api.async_response
async def ws_set_rules(hass, connection, msg):
    coordinator = _coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    await coordinator.async_set_rules(msg["person_id"], list(msg["rules"]))
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): "wake_planner/set_global",
    vol.Optional("holiday_behavior"): str,
    vol.Optional("manual_holiday_dates"): str,
    vol.Optional("calendar_entity_id"): vol.Any(str, None),
    vol.Optional("holiday_calendar_entity_id"): vol.Any(str, None),
})
@websocket_api.async_response
async def ws_set_global(hass, connection, msg):
    coordinator = _first_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_loaded", "Wake Planner not configured")
        return
    fields = {"holiday_behavior", "manual_holiday_dates", "calendar_entity_id", "holiday_calendar_entity_id"}
    updates = {k: v for k, v in msg.items() if k in fields}
    # Drop empty strings for entity ids so they go back to "not configured"
    for entity_key in ("calendar_entity_id", "holiday_calendar_entity_id"):
        if entity_key in updates and updates[entity_key] in ("", None):
            updates[entity_key] = None
    if updates:
        await coordinator.async_update_global_config(**updates)
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): "wake_planner/skip_next",
    vol.Required("person_id"): str,
})
@websocket_api.async_response
async def ws_skip_next(hass, connection, msg):
    coordinator = _coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    await coordinator.async_skip_next(msg["person_id"])
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): "wake_planner/set_override",
    vol.Required("person_id"): str,
    vol.Required("wake_time"): str,
    vol.Optional("until"): vol.Any(str, None),
})
@websocket_api.async_response
async def ws_set_override(hass, connection, msg):
    coordinator = _coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    await coordinator.async_set_override(msg["person_id"], msg["wake_time"], msg.get("until"))
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): "wake_planner/clear_override",
    vol.Required("person_id"): str,
})
@websocket_api.async_response
async def ws_clear_override(hass, connection, msg):
    coordinator = _coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    await coordinator.async_clear_override(msg["person_id"])
    connection.send_result(msg["id"], _serialise_state(coordinator))
