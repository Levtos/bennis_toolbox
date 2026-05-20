"""Constants for plug_policy_engine."""
from __future__ import annotations

DOMAIN = "plug_policy_engine"

PLATFORMS = ["sensor", "binary_sensor"]

# Policy types
POLICY_AO = "AO"          # Always On
POLICY_HB = "HB"          # Home Baseline
POLICY_AC = "AC"          # Away Cut
POLICY_SC = "SC"          # Schedule Context
POLICY_CS = "CS"          # Charging Safe
POLICY_SPECIAL = "SPECIAL"

ALL_POLICIES = [POLICY_AO, POLICY_HB, POLICY_AC, POLICY_SC, POLICY_CS, POLICY_SPECIAL]

# Device kinds (drive special branches in the engine)
KIND_GENERIC = "generic"
KIND_PC = "pc"
KIND_DENON = "denon"
KIND_H14_DOCK = "h14_dock"
KIND_APPLIANCE = "appliance"          # washing machine / dryer / dishwasher
KIND_COFFEE = "coffee_maker"
KIND_BIAS_LIGHT = "bias_light"
KIND_DIFFUSER = "diffuser"
KIND_TABLET = "tablet"

ALL_KINDS = [
    KIND_GENERIC, KIND_PC, KIND_DENON, KIND_H14_DOCK, KIND_APPLIANCE,
    KIND_COFFEE, KIND_BIAS_LIGHT, KIND_DIFFUSER, KIND_TABLET,
]

# Presence values (project convention)
PRESENCE_HOME = "zuhause"
PRESENCE_AWAY = "abwesend"
PRESENCE_AT_PARENTS = "bei_eltern"   # treated as home for cut purposes

# Bio
BIO_AWAKE = "awake"
BIO_SLEEP = "sleep"

# Day phases
DAY_MORNING = "morning"
DAY_DAY = "day"
DAY_EVENING = "evening"
DAY_NIGHT = "night"

# Unknown-power behavior
UNK_ASSUME_ACTIVE = "assume_active"
UNK_ASSUME_IDLE = "assume_idle"

# Desired switch state
DESIRED_ON = "on"
DESIRED_OFF = "off"
DESIRED_KEEP = "keep"

# Config-entry keys
CONF_DEVICES = "devices"
CONF_NAME = "name"
CONF_SWITCH = "switch_entity"
CONF_POWER = "power_entity"
CONF_BATTERY = "battery_entity"
CONF_POLICY = "policy"
CONF_KIND = "kind"
CONF_ACTIVE_THRESHOLD = "active_threshold"
CONF_IDLE_THRESHOLD = "idle_threshold"
CONF_DEADBAND_LOW = "deadband_lower"
CONF_DEADBAND_HIGH = "deadband_upper"
CONF_STABLE_OFF = "stable_off_seconds"
CONF_UNKNOWN = "unknown_behavior"
CONF_ALLOWED_CONTEXTS = "allowed_contexts"
CONF_NEVER_CUT_ACTIVE = "never_cut_when_active"
CONF_WAKE_SIGNAL_ONLY = "wake_signal_only"
CONF_TABLET_LOW = "tablet_low"
CONF_TABLET_HIGH = "tablet_high"
CONF_DIFFUSER_ON_MIN = "diffuser_on_minutes"
CONF_DIFFUSER_OFF_MIN = "diffuser_off_minutes"
CONF_MANUAL_COOLDOWN = "manual_on_cooldown_seconds"

# Global selectors
CONF_PRESENCE = "presence_entity"
CONF_BIO = "bio_entity"
CONF_DAY = "day_entity"
CONF_MEDIA = "media_context_entity"
CONF_ENTERTAINMENT = "entertainment_active_entity"
CONF_ACTIVITY = "activity_entity"

# Behavior
CONF_ENABLE_CONTROL = "enable_control"  # if False: only decision sensors
CONF_SCAN_INTERVAL = "scan_interval"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_state"

DEFAULT_SCAN_INTERVAL = 30
DEFAULT_STABLE_OFF = 600          # 10 min
DEFAULT_MANUAL_COOLDOWN = 900     # 15 min PC manual-on guard
DEFAULT_TABLET_LOW = 40
DEFAULT_TABLET_HIGH = 80
DEFAULT_DIFFUSER_ON = 15
DEFAULT_DIFFUSER_OFF = 15
DEFAULT_ACTIVE_THRESHOLD = 5.0    # W
DEFAULT_IDLE_THRESHOLD = 2.0      # W
