"""Runtime-Lookup-Helfer für das Title-Classifier-Modul."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from ...const import DATA_ENTRIES, DOMAIN
from .const import MODULE_ID
from .runtime import WatcherRuntime


def runtime_from_hass(hass: HomeAssistant, entry_id: str) -> WatcherRuntime | None:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry_id)
    if not bucket:
        return None
    return bucket.get("runtime")


def require_runtime(hass: HomeAssistant, entry_id: str) -> WatcherRuntime:
    runtime = runtime_from_hass(hass, entry_id)
    if runtime is None:
        raise ServiceValidationError(
            f"Unknown Title Classifier watcher entry_id: {entry_id}"
        )
    return runtime


def all_runtimes(hass: HomeAssistant) -> list[WatcherRuntime]:
    out: list[WatcherRuntime] = []
    for bucket in hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).values():
        if bucket.get("module_id") != MODULE_ID:
            continue
        rt = bucket.get("runtime")
        if rt is not None:
            out.append(rt)
    return out
