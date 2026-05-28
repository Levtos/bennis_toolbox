"""Konstanten für Benni Core · Devices.

Alle Werte stammen direkt aus dem Lastenheft `device_core/lastenheft.md`
(v0.2, 2026-05-27).
"""

from __future__ import annotations

from enum import Enum
from typing import Final

MODULE_ID: Final[str] = "benni_core_devices"
NAME: Final[str] = "Benni Core · Devices"
STORAGE_VERSION: Final[int] = 1


# ─────────────────────────────────────────────────────────────────────────────
# DEVICE-TYPEN (LH §6)
# ─────────────────────────────────────────────────────────────────────────────


class DeviceType(str, Enum):
    """Unterstützte Device-Typen laut LH §6."""

    TV = "tv"
    AV_RECEIVER = "av_receiver"
    CONSOLE = "console"
    SPEAKER = "speaker"
    PLUG = "plug"
    LIGHT = "light"
    COVER = "cover"
    CLIMATE = "climate"
    SENSOR_WRAPPER = "sensor_wrapper"


DEVICE_TYPE_SLUGS: Final[tuple[str, ...]] = tuple(t.value for t in DeviceType)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG FLOW KEYS
# ─────────────────────────────────────────────────────────────────────────────

# Pflicht-Felder (alle Device-Typen)
CONF_DEVICE_TYPE: Final[str] = "device_type"
CONF_SLUG: Final[str] = "slug"
CONF_DISPLAY_NAME: Final[str] = "display_name"

# Slot-Felder — Pflicht/Optional je nach Typ, siehe device_types.py
CONF_INTEGRATION_ENTITY: Final[str] = "integration_entity"  # media_player etc.
CONF_POWER_ENTITY: Final[str] = "power_entity"  # binary_sensor power on
CONF_STATUS_ENTITY: Final[str] = "status_entity"  # console: network / sub-state
CONF_TITLE_ENTITY: Final[str] = "title_entity"  # console: current title
CONF_WATT_SENSOR: Final[str] = "watt_sensor"  # numeric power sensor
CONF_WIFI_SENSOR: Final[str] = "wifi_sensor"  # connectivity diag
CONF_SWITCH_ENTITY: Final[str] = "switch_entity"  # plug switch
CONF_LIGHT_ENTITY: Final[str] = "light_entity"
CONF_COVER_ENTITY: Final[str] = "cover_entity"
CONF_POSITION_ENTITY: Final[str] = "position_entity"  # cover position separat
CONF_CLIMATE_ENTITY: Final[str] = "climate_entity"  # Thermostat (climate domain)
CONF_VALUE_ENTITY: Final[str] = "value_entity"  # sensor_wrapper

# Knöpfe / Runtime
CONF_WATT_THRESHOLD_ON: Final[str] = "watt_threshold_on"
CONF_WATT_BUCKETS: Final[str] = "watt_buckets"  # Liste {max?, state}
CONF_STICKY_HOLD_SECONDS: Final[str] = "sticky_hold_seconds"
CONF_EXPOSE_SECONDARY_SENSORS: Final[str] = "expose_secondary_sensors"

# Bulk-Import (Config-Flow, R-DC-08)
CONF_BULK_YAML: Final[str] = "bulk_yaml"

# Single-Hub: Geräte-Liste in entry.options. Dict {slug: device_conf}.
CONF_DEVICES: Final[str] = "devices"

# Feld-Maske: Multi-Select welche Slots der User belegen will
CONF_FIELDS: Final[str] = "fields"

# Watt-Bucket-Zeilen im Config-Flow (3 feste Zeilen mit Operator + Wert).
# Leerer Wert = Zeile deaktiviert.
CONF_WATT_OFF_OP: Final[str] = "watt_off_op"
CONF_WATT_OFF_VALUE: Final[str] = "watt_off_value"
CONF_WATT_IDLE_OP: Final[str] = "watt_idle_op"
CONF_WATT_IDLE_VALUE: Final[str] = "watt_idle_value"
CONF_WATT_PLAYING_OP: Final[str] = "watt_playing_op"
CONF_WATT_PLAYING_VALUE: Final[str] = "watt_playing_value"

# Operatoren für Watt-Buckets (gespiegelt aus logic.WATT_OPERATORS).
WATT_OPERATOR_CHOICES: Final[tuple[str, ...]] = ("<", "<=", "=", ">", ">=")

# Defaults
DEFAULT_WATT_THRESHOLD_ON: Final[int] = 5
DEFAULT_STICKY_HOLD_SECONDS: Final[int] = 30
DEFAULT_EXPOSE_SECONDARY_SENSORS: Final[bool] = False

# Boot-Phase ohne Sticky-Hold (R-DC-09)
BOOT_INITIAL_PHASE_SECONDS: Final[int] = 30

# Available-Frische-Fenster (R-DC-03)
AVAILABILITY_FRESHNESS_SECONDS: Final[int] = 600  # 10 min


# ─────────────────────────────────────────────────────────────────────────────
# POWER-STATE Enum (R-DC-06)
# ─────────────────────────────────────────────────────────────────────────────


class PowerState(str, Enum):
    OFF = "off"
    STANDBY = "standby"
    IDLE = "idle"
    PLAYING = "playing"
    UNKNOWN = "unknown"


POWER_STATE_SLUGS: Final[tuple[str, ...]] = tuple(s.value for s in PowerState)


# ─────────────────────────────────────────────────────────────────────────────
# POWER-SOURCE Enum (welche Quelle hat `powered` bestimmt)
# ─────────────────────────────────────────────────────────────────────────────


class PowerSource(str, Enum):
    INTEGRATION = "integration"
    WATT_FALLBACK = "watt_fallback"
    STICKY_HOLD = "sticky_hold"
    OVERRIDE = "override"
    NONE = "none"


# ─────────────────────────────────────────────────────────────────────────────
# STORAGE KEYS (per Device)
# ─────────────────────────────────────────────────────────────────────────────

# Storage payload schema:
#   {
#     "last_powered": bool | null,
#     "last_powered_change": ISO-datetime | null,
#     "override": {
#       "powered": bool | null,
#       "power_state": str | null,
#       "expires_at": ISO-datetime | null,
#     } | null,
#   }
STORAGE_KEY_LAST_POWERED: Final[str] = "last_powered"
STORAGE_KEY_LAST_POWERED_CHANGE: Final[str] = "last_powered_change"
STORAGE_KEY_OVERRIDE: Final[str] = "override"
STORAGE_KEY_OVERRIDE_POWERED: Final[str] = "powered"
STORAGE_KEY_OVERRIDE_POWER_STATE: Final[str] = "power_state"
STORAGE_KEY_OVERRIDE_EXPIRES_AT: Final[str] = "expires_at"


# ─────────────────────────────────────────────────────────────────────────────
# SERVICES (R-DC-07, R-DC-08)
# ─────────────────────────────────────────────────────────────────────────────

SERVICE_SET_OVERRIDE: Final[str] = "set_override"
SERVICE_CLEAR_OVERRIDE: Final[str] = "clear_override"

# Service-Parameter (Override). Bulk-Import läuft über den Config-Flow,
# nicht über einen Service — siehe flow.py.
ATTR_SLUG: Final[str] = "slug"
ATTR_POWERED: Final[str] = "powered"
ATTR_POWER_STATE: Final[str] = "power_state"
ATTR_EXPIRE_SECONDS: Final[str] = "expire_seconds"


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE-INTERVALL
# ─────────────────────────────────────────────────────────────────────────────

# Coordinator pollt minütlich für Available-Refresh + Override-Expiry-Check.
# State-Changes der Slot-Entities bypassen das Intervall via Event-Listener.
UPDATE_INTERVAL_SECONDS: Final[int] = 60
