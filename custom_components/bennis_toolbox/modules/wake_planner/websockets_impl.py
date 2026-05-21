"""WebSocket-Befehle des Wake-Planner-Moduls.

Alle Befehle laufen unter `bennis_toolbox/wake_planner/<command>`. Die Umbrella
registriert sie über die `WEBSOCKETS`-Liste, die `__init__.py` re-exportiert.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ...const import websocket_type
from .const import (
    CONF_HOLIDAY_BEHAVIOR,
    CONF_MANUAL_HOLIDAY_DATES,
    HOLIDAY_SKIP,
    MODULE_ID,
)
from .coordinator import (
    WakePlannerCoordinator,
    all_wake_planner_coordinators,
    coordinator_for_person,
)


def _wt(cmd: str) -> str:
    return websocket_type(MODULE_ID, cmd)


def _first(hass: HomeAssistant) -> WakePlannerCoordinator | None:
    items = all_wake_planner_coordinators(hass)
    return items[0] if items else None


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


@websocket_api.websocket_command({vol.Required("type"): _wt("get_state")})
@websocket_api.async_response
async def ws_get_state(hass, connection, msg):
    coordinator = _first(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_loaded", "Wake Planner not configured")
        return
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): _wt("get_schedule"),
    vol.Optional("days", default=14): vol.All(int, vol.Range(min=1, max=60)),
})
@websocket_api.async_response
async def ws_get_schedule(hass, connection, msg):
    coordinator = _first(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_loaded", "Wake Planner not configured")
        return
    schedule = await coordinator.async_get_schedule(msg.get("days", 14))
    connection.send_result(msg["id"], {"schedule": schedule})


@websocket_api.websocket_command({
    vol.Required("type"): _wt("add_person"),
    vol.Required("name"): str,
    vol.Optional("person_entity_id"): vol.Any(str, None),
})
@websocket_api.async_response
async def ws_add_person(hass, connection, msg):
    coordinator = _first(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_loaded", "Wake Planner not configured")
        return
    slug = await coordinator.async_add_person(msg["name"], msg.get("person_entity_id"))
    connection.send_result(msg["id"], {"slug": slug, **_serialise_state(coordinator)})


@websocket_api.websocket_command({
    vol.Required("type"): _wt("remove_person"),
    vol.Required("person_id"): str,
})
@websocket_api.async_response
async def ws_remove_person(hass, connection, msg):
    coordinator = coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    await coordinator.async_remove_person(msg["person_id"])
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): _wt("update_person"),
    vol.Required("person_id"): str,
    vol.Optional("name"): str,
    vol.Optional("person_entity_id"): vol.Any(str, None),
    vol.Optional("wake_window_minutes"): vol.All(int, vol.Range(min=1, max=120)),
    vol.Optional("routine_duration_minutes"): vol.All(int, vol.Range(min=0, max=240)),
    vol.Optional("calendar_conflict_behavior"): vol.In(["ignore", "warn_only", "wake_earlier"]),
})
@websocket_api.async_response
async def ws_update_person(hass, connection, msg):
    coordinator = coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    updates = {
        k: v for k, v in msg.items()
        if k in {
            "name",
            "person_entity_id",
            "wake_window_minutes",
            "routine_duration_minutes",
            "calendar_conflict_behavior",
        }
    }
    if updates:
        await coordinator.async_update_person(msg["person_id"], **updates)
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): _wt("set_rules"),
    vol.Required("person_id"): str,
    vol.Required("rules"): list,
})
@websocket_api.async_response
async def ws_set_rules(hass, connection, msg):
    coordinator = coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    await coordinator.async_set_rules(msg["person_id"], list(msg["rules"]))
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): _wt("set_global"),
    vol.Optional("holiday_behavior"): str,
    vol.Optional("manual_holiday_dates"): str,
    vol.Optional("calendar_entity_id"): vol.Any(str, None),
    vol.Optional("holiday_calendar_entity_id"): vol.Any(str, None),
})
@websocket_api.async_response
async def ws_set_global(hass, connection, msg):
    coordinator = _first(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_loaded", "Wake Planner not configured")
        return
    fields = {"holiday_behavior", "manual_holiday_dates", "calendar_entity_id", "holiday_calendar_entity_id"}
    updates = {k: v for k, v in msg.items() if k in fields}
    for entity_key in ("calendar_entity_id", "holiday_calendar_entity_id"):
        if entity_key in updates and updates[entity_key] in ("", None):
            updates[entity_key] = None
    if updates:
        await coordinator.async_update_global_config(**updates)
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): _wt("skip_next"),
    vol.Required("person_id"): str,
})
@websocket_api.async_response
async def ws_skip_next(hass, connection, msg):
    coordinator = coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    await coordinator.async_skip_next(msg["person_id"])
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): _wt("set_override"),
    vol.Required("person_id"): str,
    vol.Required("wake_time"): str,
    vol.Optional("until"): vol.Any(str, None),
})
@websocket_api.async_response
async def ws_set_override(hass, connection, msg):
    coordinator = coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    await coordinator.async_set_override(msg["person_id"], msg["wake_time"], msg.get("until"))
    connection.send_result(msg["id"], _serialise_state(coordinator))


@websocket_api.websocket_command({
    vol.Required("type"): _wt("clear_override"),
    vol.Required("person_id"): str,
})
@websocket_api.async_response
async def ws_clear_override(hass, connection, msg):
    coordinator = coordinator_for_person(hass, msg["person_id"])
    if not coordinator:
        connection.send_error(msg["id"], "unknown_person", "Unknown person")
        return
    await coordinator.async_clear_override(msg["person_id"])
    connection.send_result(msg["id"], _serialise_state(coordinator))


WEBSOCKETS = [
    ws_get_state,
    ws_get_schedule,
    ws_add_person,
    ws_remove_person,
    ws_update_person,
    ws_set_rules,
    ws_set_global,
    ws_skip_next,
    ws_set_override,
    ws_clear_override,
]
