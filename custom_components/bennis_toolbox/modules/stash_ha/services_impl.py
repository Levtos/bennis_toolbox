"""Services für Stash HA.

Registriert unter `bennis_toolbox.stash_ha_<action>`. Die metadata_*-Services
sind serverweite Operationen und fanten an alle geladenen Stash-Instanzen aus.
`generate_screenshot` und `save_activity` arbeiten pro Scene; der Aufrufer
adressiert mit `scene_id` einen Scene, der Service ruft den Mutate auf jedem
geladenen Client (Stash-Scene-IDs sind serverlokal eindeutig).
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from ...services import ServiceDef
from .const import (
    SERVICE_GENERATE_SCREENSHOT,
    SERVICE_METADATA_AUTO_TAG,
    SERVICE_METADATA_CLEAN,
    SERVICE_METADATA_GENERATE,
    SERVICE_METADATA_IDENTIFY,
    SERVICE_METADATA_SCAN,
    SERVICE_SAVE_ACTIVITY,
)
from .coordinator import all_stash_runtimes


_SCENE_SCHEMA = vol.Schema({vol.Required("scene_id"): cv.string})
_SAVE_ACTIVITY_SCHEMA = vol.Schema({
    vol.Required("scene_id"): cv.string,
    vol.Required("position"): vol.All(vol.Coerce(float), vol.Range(min=0)),
})


def _clients(hass: HomeAssistant) -> list:
    return [rt["client"] for rt in all_stash_runtimes(hass) if "client" in rt]


def _coords(hass: HomeAssistant) -> list:
    out = []
    for rt in all_stash_runtimes(hass):
        c = rt.get("playback")
        if c is not None:
            out.append(c)
    return out


async def _metadata_scan(hass: HomeAssistant, _call: ServiceCall) -> None:
    for c in _clients(hass):
        await c.metadata_scan()


async def _metadata_clean(hass: HomeAssistant, _call: ServiceCall) -> None:
    for c in _clients(hass):
        await c.metadata_clean()


async def _metadata_generate(hass: HomeAssistant, _call: ServiceCall) -> None:
    for c in _clients(hass):
        await c.metadata_generate()


async def _metadata_auto_tag(hass: HomeAssistant, _call: ServiceCall) -> None:
    for c in _clients(hass):
        await c.metadata_auto_tag()


async def _metadata_identify(hass: HomeAssistant, _call: ServiceCall) -> None:
    for c in _clients(hass):
        await c.metadata_identify()


async def _generate_screenshot(hass: HomeAssistant, call: ServiceCall) -> None:
    scene_id = str(call.data["scene_id"])
    for c in _clients(hass):
        await c.generate_screenshot(scene_id)
    # Refresh playback so the new screenshot URL is picked up.
    for coord in _coords(hass):
        await coord.async_request_refresh()


async def _save_activity(hass: HomeAssistant, call: ServiceCall) -> None:
    scene_id = str(call.data["scene_id"])
    position = float(call.data["position"])
    for c in _clients(hass):
        await c.save_activity(scene_id, position)
    for coord in _coords(hass):
        await coord.async_request_refresh()


SERVICES: dict[str, ServiceDef] = {
    SERVICE_METADATA_SCAN: ServiceDef(handler=_metadata_scan),
    SERVICE_METADATA_CLEAN: ServiceDef(handler=_metadata_clean),
    SERVICE_METADATA_GENERATE: ServiceDef(handler=_metadata_generate),
    SERVICE_METADATA_AUTO_TAG: ServiceDef(handler=_metadata_auto_tag),
    SERVICE_METADATA_IDENTIFY: ServiceDef(handler=_metadata_identify),
    SERVICE_GENERATE_SCREENSHOT: ServiceDef(
        handler=_generate_screenshot, schema=_SCENE_SCHEMA,
    ),
    SERVICE_SAVE_ACTIVITY: ServiceDef(
        handler=_save_activity, schema=_SAVE_ACTIVITY_SCHEMA,
    ),
}
