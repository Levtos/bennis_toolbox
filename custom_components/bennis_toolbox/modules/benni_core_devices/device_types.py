"""Device-Typ-Profile (LH §6).

Pro Typ deklarativ: welche Slots Pflicht sind, welche optional, welche
Attribute am Haupt-Sensor erscheinen, welcher Slot die Integration-Truth
liefert (für R-DC-01) und welcher den `media_player`-State trägt.

HA-frei — wird sowohl im Config-Flow als auch in der Logik benutzt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final

from .const import (
    CONF_DEVICE_TYPE,
    CONF_DISPLAY_NAME,
    CONF_SLUG,
    CONF_COVER_ENTITY,
    CONF_INTEGRATION_ENTITY,
    CONF_LIGHT_ENTITY,
    CONF_POSITION_ENTITY,
    CONF_POWER_ENTITY,
    CONF_STATUS_ENTITY,
    CONF_SWITCH_ENTITY,
    CONF_TITLE_ENTITY,
    CONF_VALUE_ENTITY,
    CONF_WATT_SENSOR,
    CONF_WIFI_SENSOR,
    DeviceType,
)


@dataclass(frozen=True)
class SlotSpec:
    """Definition eines Config-Flow-Slots."""

    key: str
    required: bool
    domains: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class DeviceTypeProfile:
    """Vollständiges Profil eines Device-Typs."""

    device_type: DeviceType
    slots: tuple[SlotSpec, ...]
    # Welcher Slot liefert die Integration-Truth für R-DC-01 (Stufe 1)?
    integration_slot: str | None
    # Welcher Slot trägt den raw-State (z.B. media_player-State) der ins
    # `media_player_state`-Attribut wandert?
    state_slot: str | None
    # Typspezifische Attribut-Schlüssel (am Haupt-Sensor zusätzlich exposed).
    extra_attributes: tuple[str, ...] = field(default_factory=tuple)
    # Ist das Gerät stateful (semantischer State über powered hinaus)?
    # Stateful: TV/AVR/Konsole/Speaker/Light/Cover.
    # Stateless: Plug, sensor_wrapper.
    stateful: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE — LH §6
# ─────────────────────────────────────────────────────────────────────────────

_TV = DeviceTypeProfile(
    device_type=DeviceType.TV,
    slots=(
        SlotSpec(CONF_INTEGRATION_ENTITY, True, ("media_player",), "TV media_player (WebOS/Sony)"),
        SlotSpec(CONF_WATT_SENSOR, False, ("sensor",), "Steckdose Watt-Sensor (Fallback)"),
        SlotSpec(CONF_WIFI_SENSOR, False, ("binary_sensor", "sensor"), "WLAN-Konnektivität"),
    ),
    integration_slot=CONF_INTEGRATION_ENTITY,
    state_slot=CONF_INTEGRATION_ENTITY,
    extra_attributes=("watt", "current_app", "wifi_online", "media_player_state"),
    stateful=True,
)

_AV_RECEIVER = DeviceTypeProfile(
    device_type=DeviceType.AV_RECEIVER,
    slots=(
        SlotSpec(CONF_INTEGRATION_ENTITY, True, ("media_player",), "AVR media_player (Denon/HEOS)"),
        SlotSpec(CONF_WATT_SENSOR, False, ("sensor",), "Steckdose Watt-Sensor (Fallback)"),
        SlotSpec(CONF_WIFI_SENSOR, False, ("binary_sensor", "sensor"), "WLAN-Konnektivität"),
    ),
    integration_slot=CONF_INTEGRATION_ENTITY,
    state_slot=CONF_INTEGRATION_ENTITY,
    extra_attributes=("watt", "current_source", "volume", "wifi_online", "media_player_state"),
    stateful=True,
)

_CONSOLE = DeviceTypeProfile(
    device_type=DeviceType.CONSOLE,
    slots=(
        SlotSpec(CONF_POWER_ENTITY, True, ("binary_sensor", "switch", "input_boolean"), "Power-Sensor (PS5/Switch an)"),
        SlotSpec(CONF_STATUS_ENTITY, False, ("media_player", "sensor"), "Status / PS Network media_player"),
        SlotSpec(CONF_TITLE_ENTITY, False, ("sensor",), "Aktueller Titel"),
        SlotSpec(CONF_WATT_SENSOR, False, ("sensor",), "Steckdose Watt-Sensor"),
    ),
    integration_slot=CONF_POWER_ENTITY,
    state_slot=CONF_STATUS_ENTITY,
    extra_attributes=("status", "title", "watt"),
    stateful=True,
)

_SPEAKER = DeviceTypeProfile(
    device_type=DeviceType.SPEAKER,
    slots=(
        SlotSpec(CONF_INTEGRATION_ENTITY, True, ("media_player",), "Speaker media_player (Sonos/HomePod)"),
        SlotSpec(CONF_WIFI_SENSOR, False, ("binary_sensor", "sensor"), "WLAN-Konnektivität"),
    ),
    integration_slot=CONF_INTEGRATION_ENTITY,
    state_slot=CONF_INTEGRATION_ENTITY,
    extra_attributes=("media_player_state", "current_track", "volume", "wifi_online"),
    stateful=True,
)

_PLUG = DeviceTypeProfile(
    device_type=DeviceType.PLUG,
    slots=(
        SlotSpec(CONF_SWITCH_ENTITY, True, ("switch", "input_boolean"), "Smart Plug Switch"),
        SlotSpec(CONF_WATT_SENSOR, False, ("sensor",), "Verbrauchsmessung"),
    ),
    integration_slot=CONF_SWITCH_ENTITY,
    state_slot=None,
    extra_attributes=("watt",),
    stateful=False,
)

_LIGHT = DeviceTypeProfile(
    device_type=DeviceType.LIGHT,
    slots=(
        SlotSpec(CONF_LIGHT_ENTITY, True, ("light",), "Light-Entität"),
    ),
    integration_slot=CONF_LIGHT_ENTITY,
    state_slot=CONF_LIGHT_ENTITY,
    extra_attributes=("brightness", "color_temp", "rgb"),
    stateful=True,
)

_COVER = DeviceTypeProfile(
    device_type=DeviceType.COVER,
    slots=(
        SlotSpec(CONF_COVER_ENTITY, True, ("cover",), "Cover-Entität"),
        SlotSpec(CONF_POSITION_ENTITY, False, ("sensor",), "Position separat (falls nötig)"),
    ),
    integration_slot=CONF_COVER_ENTITY,
    state_slot=CONF_COVER_ENTITY,
    extra_attributes=("position", "cover_state"),
    stateful=True,
)

_SENSOR_WRAPPER = DeviceTypeProfile(
    device_type=DeviceType.SENSOR_WRAPPER,
    slots=(
        SlotSpec(CONF_VALUE_ENTITY, True, ("sensor", "binary_sensor"), "Quell-Sensor"),
    ),
    integration_slot=CONF_VALUE_ENTITY,
    state_slot=CONF_VALUE_ENTITY,
    extra_attributes=("value", "unit"),
    stateful=False,
)


PROFILES: Final[dict[DeviceType, DeviceTypeProfile]] = {
    DeviceType.TV: _TV,
    DeviceType.AV_RECEIVER: _AV_RECEIVER,
    DeviceType.CONSOLE: _CONSOLE,
    DeviceType.SPEAKER: _SPEAKER,
    DeviceType.PLUG: _PLUG,
    DeviceType.LIGHT: _LIGHT,
    DeviceType.COVER: _COVER,
    DeviceType.SENSOR_WRAPPER: _SENSOR_WRAPPER,
}


def profile_for(device_type: DeviceType | str) -> DeviceTypeProfile:
    """Lookup-Helper. Akzeptiert Enum oder Slug."""
    dt = device_type if isinstance(device_type, DeviceType) else DeviceType(device_type)
    return PROFILES[dt]


def required_slot_keys(device_type: DeviceType | str) -> tuple[str, ...]:
    return tuple(s.key for s in profile_for(device_type).slots if s.required)


def all_slot_keys(device_type: DeviceType | str) -> tuple[str, ...]:
    return tuple(s.key for s in profile_for(device_type).slots)


# ─────────────────────────────────────────────────────────────────────────────
# SLUG + IMPORT-VALIDIERUNG (HA-frei, testbar)
# ─────────────────────────────────────────────────────────────────────────────

SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_]+$")


def is_valid_slug(slug: str) -> bool:
    return bool(slug) and bool(SLUG_RE.match(slug))


def validate_import_device(d: Any) -> str | None:
    """Validiert EIN Device-Dict aus dem Bulk-Import (R-DC-08).

    Returns None bei OK, sonst eine Fehler-Beschreibung (für Notification).
    """
    if not isinstance(d, dict):
        return "Eintrag ist kein Mapping"
    slug = str(d.get(CONF_SLUG, "")).strip().lower()
    if not is_valid_slug(slug):
        return f"ungültiger slug: {d.get(CONF_SLUG)!r}"
    dt_raw = d.get(CONF_DEVICE_TYPE)
    try:
        dt = DeviceType(dt_raw)
    except (ValueError, TypeError):
        return f"{slug}: unbekannter device_type {dt_raw!r}"
    for key in required_slot_keys(dt):
        if not d.get(key):
            return f"{slug}: Pflicht-Slot {key!r} fehlt"
    return None


def validate_import_payload(
    devices: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validiert die gesamte Bulk-Import-Liste (strict / all-or-nothing, OQ-10).

    Returns (valid_devices, errors). Bei nicht-leerer errors-Liste sollte der
    Aufrufer NICHTS anlegen.
    """
    if not isinstance(devices, list) or not devices:
        return ([], ["devices ist keine nicht-leere Liste"])
    errors: list[str] = []
    valid: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for idx, d in enumerate(devices):
        err = validate_import_device(d)
        if err:
            errors.append(f"#{idx + 1}: {err}")
            continue
        slug = str(d[CONF_SLUG]).strip().lower()
        if slug in seen_slugs:
            errors.append(f"#{idx + 1}: doppelter slug {slug!r}")
            continue
        seen_slugs.add(slug)
        # Normalisiere slug (lowercase/strip) + display_name-Default
        normalized = dict(d)
        normalized[CONF_SLUG] = slug
        if not normalized.get(CONF_DISPLAY_NAME):
            normalized[CONF_DISPLAY_NAME] = slug
        valid.append(normalized)
    return (valid, errors)
