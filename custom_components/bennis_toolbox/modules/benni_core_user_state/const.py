"""Konstanten für User State.

Alle Werte entstammen direkt dem Lastenheft `context_state/lastenheft.md`
(v1.1, §4.1 + R-US-01..R-US-07 + §6).
"""

from __future__ import annotations

from enum import Enum
from typing import Final

MODULE_ID: Final[str] = "benni_core_user_state"
NAME: Final[str] = "Benni Core · User State"
STORAGE_VERSION: Final[int] = 1

# ─────────────────────────────────────────────────────────────────────────────
# BIO-STATE — LH §4.1
# ─────────────────────────────────────────────────────────────────────────────


class BioState(str, Enum):
    """Die 3 Bio-States. Wert = State-Slug laut LH §4.1."""

    SLEEP = "sleep"
    WAKING = "waking"
    AWAKE = "awake"


BIO_STATE_SLUGS: Final[tuple[str, ...]] = tuple(s.value for s in BioState)

# Initial-Default für allerersten Setup (kein persistierter Zustand).
# LH §4.1: "Letzter persistierter Zustand nach HA-Restart. Kein
# Bootstrap-Override." Für allerersten Start ohne Persistenz → awake,
# weil sleep ohne expliziten Sleep-Request nie automatisch entstehen darf.
DEFAULT_BIO_STATE: Final[BioState] = BioState.AWAKE


# ─────────────────────────────────────────────────────────────────────────────
# MASTER-PHASEN-GATE für Wake-Trigger (LH R-US-06, R-US-07)
# ─────────────────────────────────────────────────────────────────────────────

# Wake-Trigger greifen nur tagsüber — schützt vor falscher Weckung wenn z.B.
# PC nachts ein Update läuft oder ein Fenster nachts kurz geöffnet wird.
# Master-Phasen aus Day State LH §4.2.
WAKE_TRIGGER_ALLOWED_MASTER_PHASES: Final[frozenset[str]] = frozenset(
    {"morning", "midday", "evening"}
)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG FLOW KEYS
# ─────────────────────────────────────────────────────────────────────────────

# Day-State-Source: liefert das `master_phase`-Attribut für Wake-Trigger-Gate.
# Default benni_core_day_state, alternativ context_day_state_combined.
CONF_DAY_STATE_SOURCE: Final[str] = "day_state_source"
DEFAULT_DAY_STATE_SOURCE: Final[str] = "sensor.benni_core_day_state"

# Wake-Trigger-Inputs (alle binary_sensor / switch / input_boolean).
CONF_PC_ACTIVE: Final[str] = "pc_active_entity"
CONF_PS5_ACTIVE: Final[str] = "ps5_active_entity"
CONF_COFFEE_ACTIVE: Final[str] = "coffee_active_entity"

# Opening-Liste: Fenster/Türen, deren state-change als Wake-Trigger zählt.
# Multi-select Entity-Picker.
CONF_OPENING_ENTITIES: Final[str] = "opening_entities"

# PC-Guard für Sleep-Eintritt (LH R-US-02). Identisch zu CONF_PC_ACTIVE
# weil derselbe PC-Sensor beide Rollen erfüllt — Slot bleibt aber separat
# benannt damit klar ist welche Funktion er gerade hat.
# (Implementation: wir nehmen einfach CONF_PC_ACTIVE auch für den Guard.)


# ─────────────────────────────────────────────────────────────────────────────
# STORAGE KEYS
# ─────────────────────────────────────────────────────────────────────────────

# Storage payload schema (persistiert):
#   {
#     "bio_state": "sleep" | "waking" | "awake",
#     "sleep_started_at": ISO-datetime | null,
#     "awake_started_at": ISO-datetime | null,
#   }
STORAGE_KEY_BIO_STATE: Final[str] = "bio_state"
STORAGE_KEY_SLEEP_STARTED_AT: Final[str] = "sleep_started_at"
STORAGE_KEY_AWAKE_STARTED_AT: Final[str] = "awake_started_at"


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE-NAMEN (LH-konform — manueller Bio-State-Override + Wake-Up-Hook)
# ─────────────────────────────────────────────────────────────────────────────

# Manuelle Bio-State-Setter — Pendant zu `script.system_mark_sleep` etc.
# aus einhornzentrale's manuellen Bio-Scripts. Diese Toolbox-Services
# führen die LH-Regeln aus (R-US-01 für set_sleep mit PC-Guard etc.).
SERVICE_SET_SLEEP: Final[str] = "set_sleep"
SERVICE_SET_WAKING: Final[str] = "set_waking"
SERVICE_SET_AWAKE: Final[str] = "set_awake"


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE-INTERVALL
# ─────────────────────────────────────────────────────────────────────────────

# Coordinator pollt minütlich um Sleep-/Awake-Dauer-Sensoren zu aktualisieren.
# State-Changes der Trigger-Entities bypass das Intervall via Event-Listener.
UPDATE_INTERVAL_SECONDS: Final[int] = 60
