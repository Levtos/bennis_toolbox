"""Konstanten des Cover-Policy-Moduls.

Position-Konvention HA-Standard: 0 = geschlossen/unten, 100 = offen/oben.
Default-Profil ist auf ein Verdunklungsrollo zugeschnitten; vom Nutzer per
Options-Flow überschreibbar.
"""
from __future__ import annotations

MODULE_ID = "cover_policy"
NAME = "Cover Policy"

# --- Modes ---
MODE_OPEN = "open"
MODE_SLEEP = "sleep"
MODE_WAKE = "wake"
MODE_PRIVACY = "privacy"
MODE_HEAT_PROTECT = "heat_protect"
MODE_GLARE_TV = "glare_tv"
MODE_GLARE_PC = "glare_pc"
MODE_WINDOW_OPEN = "window_open"
MODE_MANUAL = "manual"
ALL_MODES = [
    MODE_OPEN, MODE_SLEEP, MODE_WAKE, MODE_PRIVACY,
    MODE_HEAT_PROTECT, MODE_GLARE_TV, MODE_GLARE_PC, MODE_WINDOW_OPEN,
    MODE_MANUAL,
]
PROFILE_MODES = [
    MODE_OPEN, MODE_SLEEP, MODE_WAKE, MODE_PRIVACY,
    MODE_HEAT_PROTECT, MODE_GLARE_TV, MODE_GLARE_PC, MODE_WINDOW_OPEN,
]

# --- Config keys ---
CONF_NAME = "name"
CONF_COVER_ENTITY = "cover_entity"
# Source entities — alle optional
CONF_WINDOW_STATE = "window_state_entity"
CONF_BIO_STATE = "bio_state_entity"
CONF_PRESENCE_HOUSEHOLD = "presence_household_entity"
CONF_DAY_STATE = "day_state_entity"
CONF_DAY_CONTEXT = "day_context_entity"
CONF_PRESENCE_PERSONAL = "presence_personal_entity"
CONF_LUX = "lux_entity"
CONF_SUN = "sun_entity"
CONF_WEATHER = "weather_entity"
CONF_MEDIA_CONTEXT = "media_context_entity"
CONF_GAMING_SOURCE = "gaming_source_entity"
CONF_HEAT_PROTECT_ACTIVE = "heat_protect_entity"
# Options
CONF_APPLY_ENABLED = "apply_enabled"
CONF_MANUAL_OVERRIDE_DURATION = "manual_override_duration"
CONF_STARTUP_BLOCK_SECONDS = "startup_block_seconds"
CONF_PROFILE = "position_profile"

# --- Defaults ---
DEFAULT_APPLY_ENABLED = False
DEFAULT_MANUAL_OVERRIDE_DURATION = 1800   # 30 min
DEFAULT_STARTUP_BLOCK_SECONDS = 60
DEFAULT_RECENT_APPLY_GUARD_SECONDS = 8    # within this window the cover's
                                          # state change is "us", not the user

# Default profile (0=closed, 100=open).
DEFAULT_PROFILE: dict[str, int] = {
    MODE_OPEN:         100,
    MODE_SLEEP:        0,
    MODE_WAKE:         70,
    MODE_PRIVACY:      30,
    MODE_HEAT_PROTECT: 0,
    MODE_GLARE_TV:     20,
    MODE_GLARE_PC:     40,
    MODE_WINDOW_OPEN:  70,
}

# Lux-Schwellwert ab dem (zusammen mit day_state) Glare-Modi aktiv werden.
DEFAULT_GLARE_LUX_THRESHOLD = 5000

# --- Services ---
SERVICE_APPLY_NOW = "apply_now"
SERVICE_SET_MANUAL_OVERRIDE = "set_manual_override"
SERVICE_CLEAR_MANUAL_OVERRIDE = "clear_manual_override"
SERVICE_SET_POSITION_PROFILE = "set_position_profile"

# --- Entity unique-id suffixes ---
UID_MODE = "mode"
UID_TARGET = "target_position"
UID_REASON = "policy_reason"
UID_APPLY_BLOCKED = "apply_blocked"
UID_DEBUG = "debug"

# --- Storage ---
STORAGE_VERSION = 1

# --- Bio-/Day-/Context-Werte (Konsumiert aus benni_context-Outputs) ---
BIO_SLEEP = "sleep"
BIO_WAKING = "waking"
BIO_AWAKE = "awake"

DAY_NIGHT_LIKE = {"early_night", "late_night", "night"}
DAY_DAYTIME = {"late_morning", "forenoon", "afternoon", "day"}

PRESENCE_HOME = "zuhause"
PRESENCE_PARENTS = "bei_eltern"
PRESENCE_AWAY = "abwesend"
HOUSEHOLD_EMPTY = "leer"

# Media-Context-Werte, bei denen Glare auf TV-Seite plausibel ist.
TV_MEDIA_CONTEXTS = {"tv", "streaming", "movie"}
