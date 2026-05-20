"""Constants for notification_router."""
from __future__ import annotations

DOMAIN = "notification_router"

# --- Event bus ---
EVENT_ROUTED = "notification_router_event"

# --- Config keys: context entity sources ---
CONF_BIO_STATE = "bio_state_entity"
CONF_ACTIVITY_STATE = "activity_state_entity"
CONF_PRESENCE_PERSONAL = "presence_personal_entity"
CONF_MEDIA_CONTEXT = "media_context_entity"
CONF_HEADSET_ACTIVE = "headset_active_entity"
CONF_QUIET_MODE_ACTIVE = "quiet_mode_active_entity"
CONF_DOORBELL_STATE = "doorbell_state_entity"
CONF_OPENING_SAFETY = "opening_safety_entity"
CONF_LOCK_BATTERY = "lock_battery_entity"

# --- Config keys: optional output targets ---
CONF_NOTIFY_TARGETS = "notify_targets"          # list[str] of notify.<service> names
CONF_LIGHT_SCRIPT = "light_script"              # script.* / scene.*
CONF_MEDIA_SCRIPT = "media_script"              # script.*

# --- Options keys ---
OPT_QUIET_HOURS_START = "quiet_hours_start"
OPT_QUIET_HOURS_END = "quiet_hours_end"
OPT_SLEEP_BEHAVIOR = "sleep_behavior"           # silent|soft|critical_only
OPT_PRIVATE_TIME_BEHAVIOR = "private_time_behavior"  # mask|suppress|normal
OPT_HEADSET_BEHAVIOR = "headset_behavior"       # light_push|push_only|normal
OPT_SEVERITY_MAP = "severity_map"               # dict[event_class -> severity]
OPT_COOLDOWNS = "cooldowns"                     # dict[event_class -> seconds]
OPT_RATE_LIMIT = "rate_limit_per_minute"

# --- Bio states ---
BIO_SLEEP = "sleep"
BIO_WAKING = "waking"
BIO_AWAKE = "awake"
BIO_STATES = [BIO_SLEEP, BIO_WAKING, BIO_AWAKE]

# --- Activity states ---
ACT_IDLE = "idle"
ACT_FREE_TIME = "free_time"
ACT_WORK_HOME = "work_home"
ACT_WORK_AWAY = "work_away"
ACT_PRIVATE_TIME = "private_time"
ACT_HOUSEHOLD = "household"
ACTIVITY_STATES = [
    ACT_IDLE, ACT_FREE_TIME, ACT_WORK_HOME, ACT_WORK_AWAY,
    ACT_PRIVATE_TIME, ACT_HOUSEHOLD,
]

# --- Presence ---
PRES_HOME = "zuhause"
PRES_PARENTS = "bei_eltern"
PRES_AWAY = "abwesend"
PRESENCE_STATES = [PRES_HOME, PRES_PARENTS, PRES_AWAY]
HOME_EQUIVALENT_PRESENCE = {PRES_HOME, PRES_PARENTS}

# --- Event classes ---
EC_DOORBELL = "doorbell"
EC_SECURITY = "security"
EC_APPLIANCE_DONE = "appliance_done"
EC_DEVICE_HEALTH = "device_health"
EC_LOCK = "lock"
EC_CLIMATE = "climate"
EC_MEDIA = "media"
EC_INFO = "info"
EVENT_CLASSES = [
    EC_DOORBELL, EC_SECURITY, EC_APPLIANCE_DONE, EC_DEVICE_HEALTH,
    EC_LOCK, EC_CLIMATE, EC_MEDIA, EC_INFO,
]

# --- Severities ---
SEV_INFO = "info"
SEV_NORMAL = "normal"
SEV_URGENT = "urgent"
SEV_CRITICAL = "critical"
SEVERITIES = [SEV_INFO, SEV_NORMAL, SEV_URGENT, SEV_CRITICAL]
SEVERITY_ORDER = {s: i for i, s in enumerate(SEVERITIES)}

# --- Notification modes ---
MODE_SILENT = "silent"
MODE_SOFT = "soft"
MODE_NORMAL = "normal"
MODE_URGENT = "urgent"
MODE_CRITICAL = "critical"
MODES = [MODE_SILENT, MODE_SOFT, MODE_NORMAL, MODE_URGENT, MODE_CRITICAL]

# --- Routes ---
ROUTE_PUSH = "mobile_push"
ROUTE_PERSISTENT = "persistent_notification"
ROUTE_LIGHT = "light_ring"
ROUTE_MEDIA = "media_announce"
ROUTE_DASHBOARD = "dashboard_event"
ROUTE_BUS_ONLY = "bus_only"
ALL_ROUTES = [
    ROUTE_PUSH, ROUTE_PERSISTENT, ROUTE_LIGHT,
    ROUTE_MEDIA, ROUTE_DASHBOARD, ROUTE_BUS_ONLY,
]

# --- Services ---
SERVICE_ROUTE = "route"
SERVICE_CLEAR = "clear"
SERVICE_SET_DND = "set_dnd"

# --- Entity unique IDs ---
SENSOR_MODE = "benni_notification_mode"
SENSOR_LAST_EVENT = "benni_last_notification_event"
BINARY_SENSOR_DND = "benni_notification_dnd_active"

# --- Defaults ---
DEFAULT_COOLDOWNS = {
    EC_DOORBELL: 5,
    EC_SECURITY: 0,
    EC_APPLIANCE_DONE: 600,
    EC_DEVICE_HEALTH: 3600,
    EC_LOCK: 30,
    EC_CLIMATE: 300,
    EC_MEDIA: 60,
    EC_INFO: 60,
}

DEFAULT_RATE_LIMIT = 20  # per minute

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_state"
