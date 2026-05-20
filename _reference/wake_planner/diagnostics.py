"""Diagnostics for Wake Planner."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOLIDAY_CALENDAR_ENTITY_ID, DOMAIN
from .coordinator import WakePlannerCoordinator

async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: WakePlannerCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return {"error": "coordinator_not_loaded"}
    persons = []
    for person in coordinator.persons:
        runtime = coordinator.runtime_states.get(person.slug)
        decision = coordinator.data.get(person.slug) if coordinator.data else None
        persons.append({
            "slug": person.slug,
            "current_decision": decision.as_dict() if decision else None,
            "next_wake": coordinator.next_wakes.get(person.slug).isoformat() if coordinator.next_wakes.get(person.slug) else None,
            "override_active": bool(runtime and runtime.override_time),
            "skip_active": bool(runtime and runtime.skip_next),
            "calendar_source_status": coordinator.calendar_source.status.ha_calendar,
            "caldav_status": coordinator.calendar_source.status.caldav,
        })
    return {
        "persons": persons,
        "holiday_calendar": coordinator.options.get(CONF_HOLIDAY_CALENDAR_ENTITY_ID),
        "coordinator_last_update": coordinator.last_update_iso,
    }
