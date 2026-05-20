"""Service-Handler des Title-Classifier-Moduls.

Registriert über die Umbrella unter `bennis_toolbox.title_classifier_<action>`.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...services import ServiceDef
from ._lookup import all_runtimes, require_runtime
from .const import (
    ATTR_ENTRIES,
    ATTR_ENTRY_ID,
    ATTR_KEY,
    MAX_ENUM,
    MIN_ENUM,
    SERVICE_CLEAR_OLD,
    SERVICE_DELETE_ENTRY,
    SERVICE_IMPORT_ENTRIES,
    SERVICE_SET_ENUM,
)
from .runtime import normalise_user_key

IMPORT_ENTRY_SCHEMA = vol.Schema({
    vol.Required(ATTR_KEY): cv.string,
    vol.Required("enum"): vol.All(vol.Coerce(int), vol.Range(min=MIN_ENUM, max=MAX_ENUM)),
})


async def _set_enum(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime = require_runtime(hass, call.data[ATTR_ENTRY_ID])
    key = normalise_user_key(call.data[ATTR_KEY])
    await runtime.store.async_set_enum(key, call.data["enum"])
    runtime.refresh_current_enum()
    runtime.notify_listeners()


async def _delete_entry(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime = require_runtime(hass, call.data[ATTR_ENTRY_ID])
    if await runtime.store.async_delete(call.data[ATTR_KEY]):
        runtime.refresh_current_enum()
        runtime.notify_listeners()


async def _clear_old(hass: HomeAssistant, call: ServiceCall) -> None:
    entry_id = call.data.get(ATTR_ENTRY_ID)
    runtimes = [require_runtime(hass, entry_id)] if entry_id else all_runtimes(hass)
    for runtime in runtimes:
        if await runtime.store.async_clear_old(call.data["days"]):
            runtime.refresh_current_enum()
            runtime.notify_listeners()


async def _import_entries(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime = require_runtime(hass, call.data[ATTR_ENTRY_ID])
    entries = [
        {ATTR_KEY: normalise_user_key(item[ATTR_KEY]), "enum": item["enum"]}
        for item in call.data[ATTR_ENTRIES]
    ]
    await runtime.store.async_import_entries(entries)
    runtime.refresh_current_enum()
    runtime.notify_listeners()


SERVICES: dict[str, ServiceDef] = {
    SERVICE_SET_ENUM: ServiceDef(
        handler=_set_enum,
        schema=vol.Schema({
            vol.Required(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_KEY): cv.string,
            vol.Required("enum"): vol.All(vol.Coerce(int), vol.Range(min=MIN_ENUM, max=MAX_ENUM)),
        }),
    ),
    SERVICE_DELETE_ENTRY: ServiceDef(
        handler=_delete_entry,
        schema=vol.Schema({
            vol.Required(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_KEY): cv.string,
        }),
    ),
    SERVICE_CLEAR_OLD: ServiceDef(
        handler=_clear_old,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Optional("days", default=30): vol.All(vol.Coerce(int), vol.Range(min=1)),
        }),
    ),
    SERVICE_IMPORT_ENTRIES: ServiceDef(
        handler=_import_entries,
        schema=vol.Schema({
            vol.Required(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_ENTRIES): vol.All(cv.ensure_list, [IMPORT_ENTRY_SCHEMA]),
        }),
    ),
}
