"""Konstanten für Day State.

Alle Werte entstammen direkt dem Lastenheft `day_state/lastenheft.md` (v1.1).
Sie sind nicht konfigurierbar — sie sind Teil der definierten Logik.
Änderungen hier brauchen eine Lastenheft-Anpassung.
"""

from __future__ import annotations

from datetime import time
from enum import IntEnum
from typing import Final

# ─────────────────────────────────────────────────────────────────────────────
# DETAIL- UND MASTERPHASEN — LH §4
# ─────────────────────────────────────────────────────────────────────────────


class DetailPhase(IntEnum):
    """Die 8 Detailphasen. Wert = State-ID laut LH §4.1."""

    EARLY_MORNING = 1
    LATE_MORNING = 2
    FORENOON = 3
    AFTERNOON = 4
    EARLY_EVENING = 5
    LATE_EVENING = 6
    EARLY_NIGHT = 7
    LATE_NIGHT = 8

    @property
    def slug(self) -> str:
        return self.name.lower()


class MasterPhase(IntEnum):
    """Die 4 Masterphasen. Wert = Master-ID laut LH §4.2.

    Achtung: IDs sind absichtlich NICHT sequenziell mit Reihenfolge —
    night=1 (erste Phase nach Mitternacht-Konvention), morning=2, midday=3, evening=4.
    """

    NIGHT = 1
    MORNING = 2
    MIDDAY = 3
    EVENING = 4

    @property
    def slug(self) -> str:
        return self.name.lower()


DETAIL_TO_MASTER: Final[dict[DetailPhase, MasterPhase]] = {
    DetailPhase.EARLY_MORNING: MasterPhase.MORNING,
    DetailPhase.LATE_MORNING: MasterPhase.MORNING,
    DetailPhase.FORENOON: MasterPhase.MIDDAY,
    DetailPhase.AFTERNOON: MasterPhase.MIDDAY,
    DetailPhase.EARLY_EVENING: MasterPhase.EVENING,
    DetailPhase.LATE_EVENING: MasterPhase.EVENING,
    DetailPhase.EARLY_NIGHT: MasterPhase.NIGHT,
    DetailPhase.LATE_NIGHT: MasterPhase.NIGHT,
}


# Liste aller Detail-Slugs in Detail-ID-Reihenfolge (1..8) — für `options`-Attribut.
DETAIL_PHASE_SLUGS: Final[tuple[str, ...]] = tuple(p.slug for p in DetailPhase)

# Liste aller Master-Slugs in chronologischer Tagesreihenfolge (morning, midday,
# evening, night) — bewusst nicht in Master-ID-Reihenfolge, damit Konsumenten
# die natürliche Tagesabfolge sehen.
MASTER_PHASE_SLUGS_CHRONOLOGICAL: Final[tuple[str, ...]] = (
    MasterPhase.MORNING.slug,
    MasterPhase.MIDDAY.slug,
    MasterPhase.EVENING.slug,
    MasterPhase.NIGHT.slug,
)


# ─────────────────────────────────────────────────────────────────────────────
# ANKERZEITEN UND OFFSETS — LH §6
# ─────────────────────────────────────────────────────────────────────────────

ANCHOR_MORNING_BASE: Final[time] = time(4, 13)
ANCHOR_NIGHT_BASE: Final[time] = time(23, 18)

# Maximaler saisonaler Versatz beider Anker in Minuten (Dreieckskurve).
SEASONAL_AMPLITUDE_MIN: Final[int] = 15

# Mittags-/Abendanker relativ zu Solar Noon.
MIDDAY_OFFSET_HOURS: Final[int] = -3
EVENING_OFFSET_HOURS: Final[int] = 4

# Anteil von early_night am Nachtblock (saison-neutral).
LATE_NIGHT_SPLIT: Final[float] = 0.45

# Solar-Noon-Fallback wenn die konfigurierte Quelle keinen auswertbaren Wert
# liefert. Trigger setzt Attribut `solar_noon_fallback_active = True`.
SOLAR_NOON_FALLBACK: Final[time] = time(12, 46)


# ─────────────────────────────────────────────────────────────────────────────
# SAISONALE DREIECKSKURVE — LH §6
# ─────────────────────────────────────────────────────────────────────────────

# Sommer-Sonnenwende (Nordhalbkugel, Tag 172 = 21. Juni) → factor = +1.
# Winter-Sonnenwende (Tag 355 = 21. Dezember) → factor = −1.
SEASONAL_PEAK_DOY: Final[int] = 172

# Lineare Halbwellenlänge — Anzahl Tage zwischen Peak und Tal (= 365/4 ≈ 91.25,
# LH definiert explizit 91.5).
SEASONAL_HALF_PERIOD_DAYS: Final[float] = 91.5

# Rollover-Grenzen für Jahreswechsel-Fix.
SEASONAL_ROLLOVER_HIGH: Final[int] = 183
SEASONAL_ROLLOVER_LOW: Final[int] = -182
SEASONAL_ROLLOVER_DAYS: Final[int] = 365


# ─────────────────────────────────────────────────────────────────────────────
# MONATLICHE SPLIT-PROPORTIONEN — LH §6
# ─────────────────────────────────────────────────────────────────────────────

# Anteil von early_morning am Morgenblock (morning_fix … midday_start).
# Index 0 ist Sentinel-None; Index 1..12 = Januar..Dezember.
MORNING_SPLIT_BY_MONTH: Final[tuple[float | None, ...]] = (
    None,  # Index 0 (unbenutzt)
    0.55,  # Januar
    0.52,  # Februar
    0.47,  # März
    0.42,  # April
    0.35,  # Mai
    0.30,  # Juni
    0.30,  # Juli
    0.35,  # August
    0.40,  # September
    0.45,  # Oktober
    0.50,  # November
    0.55,  # Dezember
)

# Anteil von early_evening am Abendblock (evening_start … night_fix).
EVENING_SPLIT_BY_MONTH: Final[tuple[float | None, ...]] = (
    None,
    0.30,
    0.33,
    0.38,
    0.43,
    0.52,
    0.60,
    0.60,
    0.55,
    0.48,
    0.40,
    0.33,
    0.30,
)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG FLOW KEYS
# ─────────────────────────────────────────────────────────────────────────────

CONF_SOLAR_NOON_SOURCE: Final[str] = "solar_noon_source"

# Default: native HA-Sun-Integration. `state_attr('sun.sun', 'next_noon')` ist
# zwar weniger präzise als Sun2, aber immer verfügbar.
DEFAULT_SOLAR_NOON_SOURCE: Final[str] = "sun.sun"

# Logischer Bezeichner für Debug-Attribut `solar_noon_source` — bewusst
# entkoppelt von der Entity-ID, damit Auswechseln der Quelle nicht zu
# Verwirrung im UI führt.
SOLAR_NOON_SOURCE_FALLBACK_LABEL: Final[str] = "fallback_constant"
