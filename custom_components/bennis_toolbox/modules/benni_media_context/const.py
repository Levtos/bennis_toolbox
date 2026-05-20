"""Constants for benni_media_context."""
from __future__ import annotations

DOMAIN = "benni_media_context"
PLATFORMS = ["sensor", "binary_sensor"]

# ---- Context values ----
CTX_IDLE = "idle"
CTX_TV = "tv"
CTX_STREAMING = "streaming"
CTX_GAMING = "gaming"
CTX_PRIVATE = "private_time"

ALL_CONTEXTS = [CTX_IDLE, CTX_TV, CTX_STREAMING, CTX_GAMING, CTX_PRIVATE]

# ---- Subcontext values ----
SUB_NONE = "none"

SUB_TV_DEFAULT = "tv_default"
SUB_TV_ARD = "tv_ard"
SUB_TV_ZDF = "tv_zdf"
SUB_TV_PRO7 = "tv_pro7"
SUB_TV_RTL = "tv_rtl"

SUB_STR_DEFAULT = "streaming_default"
SUB_STR_NETFLIX = "streaming_netflix"
SUB_STR_DISNEY = "streaming_disney"
SUB_STR_PRIME = "streaming_prime"
SUB_STR_MAGENTA = "streaming_magentatv"
SUB_STR_ARD = "streaming_ard"
SUB_STR_ZDF = "streaming_zdf"
SUB_STR_YOUTUBE = "streaming_youtube"
SUB_STR_PLEX = "streaming_plex"
SUB_STR_JELLYFIN = "streaming_jellyfin"
SUB_STR_APPLETV = "streaming_appletv"
SUB_STR_RTL = "streaming_rtl"

SUB_GAME_DEFAULT = "gaming_default"
SUB_GAME_GRIND = "gaming_grind"
SUB_GAME_HEADSET = "gaming_headset"

# ---- Device values ----
DEV_NONE = "none"
DEV_TV = "tv"
DEV_APPLETV = "appletv"
DEV_PS5 = "ps5"
DEV_SWITCH = "switch"
DEV_PC = "pc"
DEV_HOMEPODS = "homepods"
DEV_DENON = "denon"

# ---- Gaming source / platform ----
GS_NONE = "none"
GS_TV = "tv"
GS_PC = "pc"

GP_NONE = "none"
GP_PS5 = "ps5"
GP_SWITCH = "switch"
GP_PC = "pc"

# ---- Title Classifier Enums ----
CLASSIFIER_GAME_DEFAULT = 0
CLASSIFIER_GAME_GRIND = 1
CLASSIFIER_GAME_HEADSET = 2

CLASSIFIER_MEDIA_NORMAL = 0
CLASSIFIER_MEDIA_BOOST = 1
CLASSIFIER_MEDIA_MUTE = 2

# ---- Config keys ----
CONF_TV_ACTIVE = "tv_active"
CONF_TV_SOURCE = "tv_source"
CONF_TV_POWER_FALLBACK = "tv_power_fallback"
CONF_APPLETV = "appletv"
CONF_PS5_STATUS = "ps5_status"
CONF_PS5_TITLE = "ps5_title"
CONF_SWITCH_DOCK = "switch_dock"
CONF_PC_ACTIVE = "pc_active"
CONF_DENON_ACTIVE = "denon_active"
CONF_HOMEPODS = "homepods"
CONF_TITLE_CLASSIFIER_PS5 = "classifier_ps5"
CONF_TITLE_CLASSIFIER_PC = "classifier_pc"
CONF_TITLE_CLASSIFIER_HOMEPODS = "classifier_homepods"
CONF_TITLE_CLASSIFIER_MEDIA = "classifier_media"
CONF_DOOR = "entry_door"
CONF_CALL_MONITOR = "call_monitor"
CONF_DAY_STATE = "day_state"
CONF_ACTIVITY_STATE = "activity_state"
CONF_WINDOW_STATE = "window_state"
CONF_APPLETV_APP_MAP = "appletv_app_map"

# Options
CONF_DEBOUNCE = "debounce_seconds"
CONF_QUIET_DUCK = "quiet_ducking_level"
CONF_BASE_VOL_HOMEPODS = "base_volume_homepods"
CONF_BASE_VOL_DENON = "base_volume_denon"
CONF_BOOST_OFFSET = "track_boost_offset"
CONF_WINDOW_OFFSET = "window_volume_offset"
CONF_SUB_WINDOWS = "subwoofer_allowed_windows"

DEFAULT_DEBOUNCE = 4.0
DEFAULT_QUIET_DUCK = 0.15
DEFAULT_BASE_VOL_HOMEPODS = 0.35
DEFAULT_BASE_VOL_DENON = 0.40
DEFAULT_BOOST_OFFSET = 0.10
DEFAULT_WINDOW_OFFSET = -0.05

DEFAULT_APPLETV_APP_MAP = {
    "com.netflix.Netflix": SUB_STR_NETFLIX,
    "com.disney.disneyplus": SUB_STR_DISNEY,
    "com.amazon.aiv.AIVApp": SUB_STR_PRIME,
    "de.telekom.magentatv": SUB_STR_MAGENTA,
    "de.ard.ardmediathek": SUB_STR_ARD,
    "de.zdf.zdfmediathek": SUB_STR_ZDF,
    "com.google.ios.youtube": SUB_STR_YOUTUBE,
    "com.plexapp.plex": SUB_STR_PLEX,
    "org.jellyfin.swiftfin": SUB_STR_JELLYFIN,
    "com.apple.TVWatchList": SUB_STR_APPLETV,
    "de.rtl.rtlnow": SUB_STR_RTL,
}

# Apple TV system app ids that should trigger pre-ATV rollback (Home, Settings, etc.)
APPLETV_SYSTEM_APPS = {
    "com.apple.TVHomeSharing",
    "com.apple.TVSettings",
    "com.apple.HomeKit",
    "com.apple.TVScreenSaver",
}

# TV source -> subcontext mapping
TV_SOURCE_MAP = {
    "ARD": SUB_TV_ARD,
    "Das Erste": SUB_TV_ARD,
    "ZDF": SUB_TV_ZDF,
    "ProSieben": SUB_TV_PRO7,
    "Pro7": SUB_TV_PRO7,
    "RTL": SUB_TV_RTL,
}

# ---- Services ----
SERVICE_FORCE_RECALCULATE = "force_recalculate"
SERVICE_SET_MANUAL_NUDGE = "set_manual_nudge"
SERVICE_CLEAR_MANUAL_NUDGE = "clear_manual_nudge"
SERVICE_START_RADIO = "start_radio"
SERVICE_STOP_MEDIA = "stop_media"

SIGNAL_UPDATE = f"{DOMAIN}_update"
