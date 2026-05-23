"""Constants for benni_media_context.

Externe HA-Domain ist `bennis_toolbox`; alle Namespaces (Storage, Service,
Event) leiten sich vom Modul-Helper aus `MODULE_ID` ab.
"""
from __future__ import annotations

MODULE_ID = "benni_media_context"
NAME = "Benni Media Context"

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

# ---------------------------------------------------------------------------
# New per-device CONF model (0.3.6+). Each device gets a thin set of
# optional entity slots; player_state + media-player attributes carry the
# rich signal, the *_active / *_power / *_ping entities only add
# plausibility / fallback signals.
#
# Legacy CONF keys above stay valid — coordinator reads new-then-legacy
# so existing config entries keep working without migration.
# ---------------------------------------------------------------------------

# TV
CONF_TV_PLAYER = "tv_player_entity"
CONF_TV_ACTIVE_NEW = "tv_active_entity"
CONF_TV_POWER = "tv_power_entity"

# Apple TV
CONF_APPLETV_PLAYER = "appletv_player_entity"

# PS5
CONF_PS5_PLAYER = "ps5_player_entity"
CONF_PS5_ACTIVE = "ps5_active_entity"
CONF_PS5_POWER = "ps5_power_entity"
CONF_PS5_TITLE_ENTITY = "ps5_title_entity"
CONF_PS5_NETWORK = "ps5_network_entity"

# Switch
CONF_SWITCH_ACTIVE = "switch_active_entity"
CONF_SWITCH_POWER = "switch_power_entity"
CONF_SWITCH_PING = "switch_ping_entity"

# PC
CONF_PC_ACTIVE_NEW = "pc_active_entity"
CONF_PC_POWER = "pc_power_entity"

# Denon
CONF_DENON_PLAYER = "denon_player_entity"
CONF_DENON_ACTIVE_NEW = "denon_active_entity"
CONF_DENON_POWER = "denon_power_entity"

# HomePods
CONF_HOMEPODS_PLAYER = "homepods_player_entity"


# Devices grouped for the per-device options-flow cards. Each card
# resolves to the listed CONF keys when rendering / saving.
DEVICE_CARDS: dict[str, tuple[str, ...]] = {
    "tv": (CONF_TV_PLAYER, CONF_TV_ACTIVE_NEW, CONF_TV_POWER),
    "appletv": (CONF_APPLETV_PLAYER,),
    "ps5": (CONF_PS5_PLAYER, CONF_PS5_ACTIVE, CONF_PS5_POWER,
            CONF_PS5_TITLE_ENTITY, CONF_PS5_NETWORK),
    "switch": (CONF_SWITCH_ACTIVE, CONF_SWITCH_POWER, CONF_SWITCH_PING),
    "pc": (CONF_PC_ACTIVE_NEW, CONF_PC_POWER),
    "denon": (CONF_DENON_PLAYER, CONF_DENON_ACTIVE_NEW, CONF_DENON_POWER),
    "homepods": (CONF_HOMEPODS_PLAYER,),
}


# Map each new key to the legacy key it supersedes (or None for purely new
# slots). Coordinator reads new-then-legacy for backward compat.
LEGACY_FALLBACKS: dict[str, str | None] = {
    CONF_TV_PLAYER: None,            # new: media_player slot
    CONF_TV_ACTIVE_NEW: CONF_TV_ACTIVE,
    CONF_TV_POWER: CONF_TV_POWER_FALLBACK,
    CONF_APPLETV_PLAYER: CONF_APPLETV,
    CONF_PS5_PLAYER: None,
    CONF_PS5_ACTIVE: CONF_PS5_STATUS,
    CONF_PS5_POWER: None,
    CONF_PS5_TITLE_ENTITY: CONF_PS5_TITLE,
    CONF_PS5_NETWORK: None,
    CONF_SWITCH_ACTIVE: CONF_SWITCH_DOCK,
    CONF_SWITCH_POWER: None,
    CONF_SWITCH_PING: None,
    CONF_PC_ACTIVE_NEW: CONF_PC_ACTIVE,
    CONF_PC_POWER: None,
    CONF_DENON_PLAYER: None,
    CONF_DENON_ACTIVE_NEW: CONF_DENON_ACTIVE,
    CONF_DENON_POWER: None,
    CONF_HOMEPODS_PLAYER: CONF_HOMEPODS,
}

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

# Events auf dem HA-Bus (gepräfixt mit der Toolbox-Domäne).
EVENT_START_RADIO = "bennis_toolbox_benni_media_context_start_radio"
EVENT_STOP_MEDIA = "bennis_toolbox_benni_media_context_stop_media"
