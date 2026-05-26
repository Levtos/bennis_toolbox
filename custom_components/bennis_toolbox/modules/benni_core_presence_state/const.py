"""Konstanten für Presence State.

Alle Werte entstammen Lastenheft Context State v1.1 §4.2-4.5, §6 und
R-PS-01..R-PS-11.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

MODULE_ID: Final[str] = "benni_core_presence_state"
NAME: Final[str] = "Benni Core · Presence State"
STORAGE_VERSION: Final[int] = 1


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT-ENUMS — LH §4.2 bis §4.5
# ─────────────────────────────────────────────────────────────────────────────


class PresencePersonal(str, Enum):
    """LH §4.2"""

    ZUHAUSE = "zuhause"
    ABWESEND = "abwesend"
    BEI_ELTERN = "bei_eltern"


class PresenceHousehold(str, Enum):
    """LH §4.3"""

    LEER = "leer"
    NICHT_LEER = "nicht_leer"


class Transition(str, Enum):
    """LH §4.4"""

    NONE = "none"
    COMING_HOME = "coming_home"
    LEAVING_HOME = "leaving_home"
    PASSING_THROUGH = "passing_through"


class Band(str, Enum):
    """LH §4.5"""

    HOME = "home"
    NEAR = "near"
    PREHEAT = "preheat"
    FAR = "far"


class Direction(str, Enum):
    """Proximity-Output, weitergereicht. `unknown` für unavailable."""

    TOWARDS = "towards"
    AWAY_FROM = "away_from"
    STATIONARY = "stationary"
    UNKNOWN = "unknown"


# Slug-Listen für SensorDeviceClass.ENUM options
PRESENCE_PERSONAL_OPTIONS: Final[tuple[str, ...]] = tuple(s.value for s in PresencePersonal)
PRESENCE_HOUSEHOLD_OPTIONS: Final[tuple[str, ...]] = tuple(s.value for s in PresenceHousehold)
TRANSITION_OPTIONS: Final[tuple[str, ...]] = tuple(s.value for s in Transition)
BAND_OPTIONS: Final[tuple[str, ...]] = tuple(s.value for s in Band)
DIRECTION_OPTIONS: Final[tuple[str, ...]] = tuple(s.value for s in Direction)


# ─────────────────────────────────────────────────────────────────────────────
# SCHWELLEN & TIMINGS — LH §6
# ─────────────────────────────────────────────────────────────────────────────

# Konfigurierbar (Optionen)
DEFAULT_HOME_RADIUS_M: Final[int] = 150
DEFAULT_NEAR_RADIUS_M: Final[int] = 250  # User-Entscheidung (a): explizit, default lt §4.5
DEFAULT_PREHEAT_RADIUS_M: Final[int] = 1500
DEFAULT_HYSTERESIS_M: Final[int] = 100
DEFAULT_PREHEAT_DURATION_S: Final[int] = 1200  # 20 Minuten

# Nicht konfigurierbar (LH-fest)
TRANSITION_HOLD_S: Final[int] = 120  # 2 Minuten
HOME_GATE_ENTRY_DELAY_S: Final[int] = 60
HOME_GATE_EXIT_DELAY_S: Final[int] = 150
FRESHNESS_ICLOUD_S: Final[int] = 900
FRESHNESS_MOBILE_S: Final[int] = 900
FRESHNESS_WLAN_S: Final[int] = 600


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG-FLOW-KEYS
# ─────────────────────────────────────────────────────────────────────────────

# Tracker-Slots (Pflicht außer wo markiert)
CONF_ICLOUD_TRACKER: Final[str] = "icloud_tracker"  # Pflicht (R-PS-01)
CONF_MOBILE_TRACKER: Final[str] = "mobile_tracker"  # optional, Fallback (R-PS-02)
CONF_WLAN_BENNI_TRACKER: Final[str] = "wlan_benni_tracker"  # Pflicht (R-PS-03 + bei_eltern)
CONF_WLAN_ELTERN_TRACKERS: Final[str] = "wlan_eltern_trackers"  # Multi-select, optional

# Proximity-Slots (Pflicht für Heimband + Preheat)
CONF_PROXIMITY_DISTANCE: Final[str] = "proximity_distance"
CONF_PROXIMITY_DIRECTION: Final[str] = "proximity_direction"

# Quellzonen für R-PS-08 Preheat-Auslösung (Multi-select Zonen, optional)
CONF_SOURCE_ZONES: Final[str] = "source_zones"

# Person-Entity für Zone-Tracking (Pflicht wenn source_zones gesetzt)
CONF_PERSON: Final[str] = "person"

# Konfigurierbare Schwellen
CONF_HOME_RADIUS_M: Final[str] = "home_radius_m"
CONF_NEAR_RADIUS_M: Final[str] = "near_radius_m"
CONF_PREHEAT_RADIUS_M: Final[str] = "preheat_radius_m"
CONF_HYSTERESIS_M: Final[str] = "hysteresis_m"
CONF_PREHEAT_DURATION_S: Final[str] = "preheat_duration_s"


# ─────────────────────────────────────────────────────────────────────────────
# STORAGE-KEYS
# ─────────────────────────────────────────────────────────────────────────────

# Persistiert über HA-Restart, damit Home-Gate-Stabilisierung und
# Preheat-Timer nicht beim Boot zurückgesetzt werden.
STORAGE_KEY_HOME_CANDIDATE: Final[str] = "home_candidate"
STORAGE_KEY_HOME_GATE: Final[str] = "home_gate"
STORAGE_KEY_LAST_BAND: Final[str] = "last_band"
STORAGE_KEY_PREHEAT_ACTIVE: Final[str] = "preheat_active"
STORAGE_KEY_PREHEAT_SOURCE: Final[str] = "preheat_source"
STORAGE_KEY_PREHEAT_STARTED_AT: Final[str] = "preheat_started_at"
STORAGE_KEY_TRANSITION_KIND: Final[str] = "transition_kind"
STORAGE_KEY_TRANSITION_STARTED_AT: Final[str] = "transition_started_at"


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE-INTERVALL
# ─────────────────────────────────────────────────────────────────────────────

# Coordinator pollt minütlich um Timer abzulaufen (Transition, Preheat,
# Home-Gate). State-Changes der Tracker-Entities bypass via Event-Listener.
UPDATE_INTERVAL_SECONDS: Final[int] = 30
