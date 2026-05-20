"""Constants for the Benni Context integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "benni_context"
PLATFORMS: Final = ["sensor", "binary_sensor"]

# --- Config entry keys -------------------------------------------------------

# Entity selectors
CONF_GPS_PRIMARY = "gps_primary"
CONF_GPS_SECONDARY = "gps_secondary"
CONF_WLAN_BENNI = "wlan_benni"
CONF_WLAN_ELTERN_1 = "wlan_eltern_1"
CONF_WLAN_ELTERN_2 = "wlan_eltern_2"
CONF_PROXIMITY_DISTANCE = "proximity_distance"
CONF_PROXIMITY_DIRECTION = "proximity_direction"
CONF_WAKE_NEXT = "wake_next"
CONF_WAKE_NEEDED = "wake_needed"
CONF_PC_ACTIVE = "pc_active"
CONF_PS5_ACTIVE = "ps5_active"
CONF_COFFEE_ACTIVE = "coffee_active"
CONF_DOOR_WAKE = "door_wake"
CONF_MEDIA_CONTEXT = "media_context"
CONF_PRIVATE_SOURCE = "private_source"
CONF_HOMEOFFICE_PING = "homeoffice_ping"
CONF_HOLIDAY_SENSOR = "holiday_sensor"
CONF_HOUSEHOLD_SOURCE = "household_source"

# Numeric thresholds (options flow)
CONF_HOME_RADIUS = "home_radius"
CONF_PREHEAT_RADIUS = "preheat_radius"
CONF_NEAR_RADIUS = "near_radius"
CONF_HYSTERESIS_M = "hysteresis_m"
CONF_PREHEAT_DURATION = "preheat_duration"
CONF_TRACKER_FRESHNESS = "tracker_freshness"
CONF_TRANSITION_HOLD = "transition_hold"

# --- Defaults ----------------------------------------------------------------

DEFAULT_HOME_RADIUS = 100  # meters
DEFAULT_PREHEAT_RADIUS = 800
DEFAULT_NEAR_RADIUS = 3000
DEFAULT_HYSTERESIS_M = 50
DEFAULT_PREHEAT_DURATION = 900  # seconds (15 min cap)
DEFAULT_TRACKER_FRESHNESS = 1800  # seconds (30 min)
DEFAULT_TRANSITION_HOLD = 120  # seconds

# --- State enums -------------------------------------------------------------

# Presence Personal
PERS_HOME = "zuhause"
PERS_PARENTS = "bei_eltern"
PERS_AWAY = "abwesend"
PRESENCE_PERSONAL_STATES = [PERS_HOME, PERS_PARENTS, PERS_AWAY]

# Presence Household
HH_EMPTY = "leer"
HH_OCCUPIED = "nicht_leer"
PRESENCE_HOUSEHOLD_STATES = [HH_EMPTY, HH_OCCUPIED]

# Presence Band
BAND_HOME = "home"
BAND_PREHEAT = "preheat"
BAND_NEAR = "near"
BAND_FAR = "far"
PRESENCE_BAND_STATES = [BAND_HOME, BAND_PREHEAT, BAND_NEAR, BAND_FAR]

# Presence Transition
TRANS_NONE = "none"
TRANS_COMING_HOME = "coming_home"
TRANS_LEAVING_HOME = "leaving_home"
TRANS_PASSING = "passing_through"
PRESENCE_TRANSITION_STATES = [
    TRANS_NONE,
    TRANS_COMING_HOME,
    TRANS_LEAVING_HOME,
    TRANS_PASSING,
]

# Bio
BIO_SLEEP = "sleep"
BIO_WAKING = "waking"
BIO_AWAKE = "awake"
BIO_STATES = [BIO_SLEEP, BIO_WAKING, BIO_AWAKE]

# Day state
DAY_EARLY_MORNING = "early_morning"
DAY_LATE_MORNING = "late_morning"
DAY_FORENOON = "forenoon"
DAY_AFTERNOON = "afternoon"
DAY_EARLY_EVENING = "early_evening"
DAY_LATE_EVENING = "late_evening"
DAY_EARLY_NIGHT = "early_night"
DAY_LATE_NIGHT = "late_night"
DAY_STATES = [
    DAY_EARLY_MORNING,
    DAY_LATE_MORNING,
    DAY_FORENOON,
    DAY_AFTERNOON,
    DAY_EARLY_EVENING,
    DAY_LATE_EVENING,
    DAY_EARLY_NIGHT,
    DAY_LATE_NIGHT,
]

# Day context
DC_WERKTAG = "werktag"
DC_WOCHENENDE = "wochenende"
DC_FREI = "frei"
DAY_CONTEXT_STATES = [DC_WERKTAG, DC_WOCHENENDE, DC_FREI]

# Activity state
ACT_IDLE = "idle"
ACT_FREE_TIME = "free_time"
ACT_WORK_HOME = "work_home"
ACT_WORK_AWAY = "work_away"
ACT_PRIVATE = "private_time"
ACT_HOUSEHOLD = "household"
ACTIVITY_STATES = [
    ACT_IDLE,
    ACT_FREE_TIME,
    ACT_WORK_HOME,
    ACT_WORK_AWAY,
    ACT_PRIVATE,
    ACT_HOUSEHOLD,
]

# --- Storage -----------------------------------------------------------------

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.state"

# Coordinator update interval (seconds). Most updates are push-driven via
# state-change listeners, but a periodic tick keeps time-dependent states
# (day_state, freshness checks, preheat expiry) accurate.
UPDATE_INTERVAL = 30
