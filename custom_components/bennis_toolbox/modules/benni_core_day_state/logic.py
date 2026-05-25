"""Reine Berechnungs-Funktionen für Day State (Lastenheft v1.1).

Diese Datei hat **keine** HA-Imports und ist vollständig in pytest testbar.
Alle Funktionen sind deterministisch über `now: datetime` und
`solar_noon: datetime | None` parametrisiert.

Verteilung der Verantwortung:
- `logic.py` (hier): pure Funktionen — Zeit rein, Phase + Attribute raus.
- `coordinator.py`: HA-Integration, Trigger-Verwaltung, Solar-Noon-Quellen-Read.
- `sensor.py`: Mapping von Logik-Output auf SensorEntity-State/Attribute.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Final

from .const import (
    ANCHOR_MORNING_BASE,
    ANCHOR_NIGHT_BASE,
    DETAIL_TO_MASTER,
    EVENING_OFFSET_HOURS,
    EVENING_SPLIT_BY_MONTH,
    LATE_NIGHT_SPLIT,
    MIDDAY_OFFSET_HOURS,
    MORNING_SPLIT_BY_MONTH,
    SEASONAL_AMPLITUDE_MIN,
    SEASONAL_HALF_PERIOD_DAYS,
    SEASONAL_PEAK_DOY,
    SEASONAL_ROLLOVER_DAYS,
    SEASONAL_ROLLOVER_HIGH,
    SEASONAL_ROLLOVER_LOW,
    SOLAR_NOON_FALLBACK,
    DetailPhase,
    MasterPhase,
)

# Detailphasen in chronologischer Reihenfolge eines logischen Tag-Zyklus.
# Beginnt mit early_morning (am morning_fix) und endet mit late_night (deren
# Start strenggenommen am Folgetag liegt). Diese Reihenfolge ist der Schlüssel
# zur sequenziellen Phasenauswertung in `compute_day_state`.
_PHASE_ORDER: Final[tuple[DetailPhase, ...]] = (
    DetailPhase.EARLY_MORNING,
    DetailPhase.LATE_MORNING,
    DetailPhase.FORENOON,
    DetailPhase.AFTERNOON,
    DetailPhase.EARLY_EVENING,
    DetailPhase.LATE_EVENING,
    DetailPhase.EARLY_NIGHT,
    DetailPhase.LATE_NIGHT,
)


@dataclass(frozen=True)
class DayStateResult:
    """Vollständiges Ergebnis einer Day-State-Berechnung.

    Alle Felder entsprechen 1:1 den Pflicht- und Debug-Attributen aus LH §13.
    Der `sensor.py`-Layer mappt das auf SensorEntity ohne weitere Logik.
    """

    # Pflicht (LH §13.1)
    detail_phase: DetailPhase
    master_phase: MasterPhase
    phase_starts: dict[str, str]  # detail-slug → "HH:MM:SS"
    master_phase_starts: dict[str, str]  # master-slug → "HH:MM:SS"
    current_phase_started_at: datetime
    next_phase: DetailPhase
    next_phase_at: datetime
    minutes_until_next_phase: int
    next_master_phase: MasterPhase | None
    next_master_phase_at: datetime | None
    solar_noon_at: datetime
    solar_noon_fallback_active: bool
    seasonal_factor: float
    seasonal_offset_minutes: float

    # Debug (LH §13.2)
    morning_fix_at: datetime
    night_fix_at: datetime
    midday_start_at: datetime
    evening_start_at: datetime
    late_morning_start_at: datetime
    late_evening_start_at: datetime
    late_night_start_at: datetime
    month_morning_split: float
    month_evening_split: float


# ─────────────────────────────────────────────────────────────────────────────
# REINE BAUSTEINE (testbar in Isolation)
# ─────────────────────────────────────────────────────────────────────────────


def seasonal_factor(doy: int) -> float:
    """Saisonaler Faktor ∈ [−1, +1] für den gegebenen Tag im Jahr (LH §6).

    Dreieckskurve mit Peak bei DOY 172 (Sommer ≈ 21. Juni) und Tal bei
    DOY 355 (Winter ≈ 21. Dezember). Implementiert den Rollover-Fix für
    den Jahreswechsel — ohne den würden Tage nach 21. Dezember falsche
    Werte liefern.
    """
    dist = doy - SEASONAL_PEAK_DOY
    if dist > SEASONAL_ROLLOVER_HIGH:
        dist -= SEASONAL_ROLLOVER_DAYS
    elif dist < SEASONAL_ROLLOVER_LOW:
        dist += SEASONAL_ROLLOVER_DAYS
    return max(-1.0, min(1.0, 1.0 - abs(dist) / SEASONAL_HALF_PERIOD_DAYS))


def seasonal_offset_seconds(doy: int) -> int:
    """Saisonaler Versatz in Sekunden — `±15 min × seasonal_factor`."""
    return int(SEASONAL_AMPLITUDE_MIN * 60 * seasonal_factor(doy))


def _doy(d: date) -> int:
    return d.timetuple().tm_yday


def _combine(d: date, t: time, tz: tzinfo | None) -> datetime:
    return datetime.combine(d, t, tzinfo=tz)


def morning_fix_for(now: datetime) -> datetime:
    """Morgenanker für den Tag von `now` — `04:13 − seasonal_offset`."""
    base = _combine(now.date(), ANCHOR_MORNING_BASE, now.tzinfo)
    return base - timedelta(seconds=seasonal_offset_seconds(_doy(now.date())))


def night_fix_for(now: datetime) -> datetime:
    """Nachtanker für den Tag von `now` — `23:18 + seasonal_offset`."""
    base = _combine(now.date(), ANCHOR_NIGHT_BASE, now.tzinfo)
    return base + timedelta(seconds=seasonal_offset_seconds(_doy(now.date())))


def midday_start_for(solar_noon: datetime) -> datetime:
    """Vormittags-Ende / Mittags-Start = `solar_noon − 3h`."""
    return solar_noon + timedelta(hours=MIDDAY_OFFSET_HOURS)


def evening_start_for(solar_noon: datetime) -> datetime:
    """Nachmittags-Ende / Abend-Start = `solar_noon + 4h`."""
    return solar_noon + timedelta(hours=EVENING_OFFSET_HOURS)


def late_morning_start_for(
    morning_fix: datetime, midday_start: datetime, month: int
) -> datetime:
    """Wechsel early_morning → late_morning nach monatlichem Morning-Split."""
    split = MORNING_SPLIT_BY_MONTH[month]
    assert split is not None  # Index 0 ist Sentinel, 1..12 valide
    return morning_fix + (midday_start - morning_fix) * split


def late_evening_start_for(
    evening_start: datetime, night_fix: datetime, month: int
) -> datetime:
    """Wechsel early_evening → late_evening nach monatlichem Evening-Split."""
    split = EVENING_SPLIT_BY_MONTH[month]
    assert split is not None
    return evening_start + (night_fix - evening_start) * split


def late_night_start_for(
    night_fix: datetime, next_day_morning_fix: datetime
) -> datetime:
    """`night_fix + 0.45 × (next_day_morning_fix − night_fix)` (LH §6)."""
    return night_fix + (next_day_morning_fix - night_fix) * LATE_NIGHT_SPLIT


# ─────────────────────────────────────────────────────────────────────────────
# HAUPTFUNKTION
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_solar_noon(
    now: datetime, solar_noon: datetime | None
) -> tuple[datetime, bool]:
    """Solar Noon oder Fallback. Gibt (timestamp, fallback_active) zurück.

    Konvertiert Solar Noon nach `now.tzinfo`, damit alle daraus abgeleiteten
    Anker (midday_start, evening_start, late_evening_start) in derselben
    Zeitzone wie morning_fix/night_fix landen. Sonst zeigt der Sensor
    Mischformate in `phase_starts` an (z.B. CEST für morning_fix, UTC für
    forenoon — weil `sun.sun.next_noon` als UTC-Timestamp parsed wird).
    """
    if solar_noon is None:
        return _combine(now.date(), SOLAR_NOON_FALLBACK, now.tzinfo), True
    if now.tzinfo is not None and solar_noon.tzinfo is not None:
        solar_noon = solar_noon.astimezone(now.tzinfo)
    return solar_noon, False


def compute_day_state(
    now: datetime, solar_noon: datetime | None
) -> DayStateResult:
    """Berechne den vollständigen Day State für den Zeitpunkt `now`.

    Args:
        now: Aktueller Zeitpunkt, lokale TZ-aware datetime.
        solar_noon: Solar Noon des heutigen Tages, oder None für Fallback (12:46).

    Returns:
        DayStateResult mit Phase + allen Pflicht- und Debug-Attributen.

    Verhalten an Tagrändern (LH §5 R3 wörtlich):
    - 00:00 bis morning_fix → late_night (auch wenn rechnerisch noch
      "gestern's early_night" wäre — bewusste Vereinfachung im LH).
    - `current_phase_started_at` in diesem Fenster wird mit "gestern's
      late_night_start" befüllt (Option i, vom User bestätigt), damit
      Konsumenten einen semantisch sinnvollen Wert sehen.
    """
    solar_noon_resolved, fallback_active = _resolve_solar_noon(now, solar_noon)
    month = now.month

    # Heutige Anker
    morning_fix = morning_fix_for(now)
    night_fix = night_fix_for(now)
    midday_start = midday_start_for(solar_noon_resolved)
    evening_start = evening_start_for(solar_noon_resolved)
    late_morning_start = late_morning_start_for(morning_fix, midday_start, month)
    late_evening_start = late_evening_start_for(evening_start, night_fix, month)

    # Folgetag-Anker für late_night_start (liegt typisch ~01:30 NEXT day).
    tomorrow = now + timedelta(days=1)
    morning_fix_tomorrow = morning_fix_for(tomorrow)
    late_night_start = late_night_start_for(night_fix, morning_fix_tomorrow)

    # Chronologische Anker-Liste für den heutigen Tag-Zyklus.
    chronological: list[tuple[DetailPhase, datetime]] = [
        (DetailPhase.EARLY_MORNING, morning_fix),
        (DetailPhase.LATE_MORNING, late_morning_start),
        (DetailPhase.FORENOON, midday_start),
        (DetailPhase.AFTERNOON, solar_noon_resolved),
        (DetailPhase.EARLY_EVENING, evening_start),
        (DetailPhase.LATE_EVENING, late_evening_start),
        (DetailPhase.EARLY_NIGHT, night_fix),
        (DetailPhase.LATE_NIGHT, late_night_start),
    ]

    # Phasenauswertung — LH §5 R3 sequenziell, erste zutreffende Bedingung
    # gewinnt.
    current_phase: DetailPhase
    current_phase_started_at: datetime
    next_phase: DetailPhase
    next_phase_at: datetime

    if now < morning_fix:
        # 00:00 – morning_fix → late_night (LH wörtlich, §5 R3 + "Wichtig").
        current_phase = DetailPhase.LATE_NIGHT
        next_phase = DetailPhase.EARLY_MORNING
        next_phase_at = morning_fix

        # Option (i, vom User bestätigt): yesterday's late_night_start als
        # Started-At — aber nur wenn er bereits in der Vergangenheit liegt.
        # Im schmalen Fenster [00:00, late_night_start_yesterday] (typisch
        # 00:00 – ~01:30) hat die LH-Simplifikation den Sensor schon auf
        # late_night geflippt, obwohl die "echte" Transition aus
        # early_night erst gleich kommt. Für dieses Fenster nehmen wir
        # Mitternacht heute — das ist der Moment, an dem LH den Phasen-
        # Wechsel tatsächlich vollzieht.
        yesterday = now - timedelta(days=1)
        night_fix_yesterday = night_fix_for(yesterday)
        late_night_start_yesterday = late_night_start_for(
            night_fix_yesterday, morning_fix
        )
        if now >= late_night_start_yesterday:
            current_phase_started_at = late_night_start_yesterday
        else:
            current_phase_started_at = _combine(now.date(), time(0, 0), now.tzinfo)
    else:
        # Default: EARLY_NIGHT (passt für now >= night_fix und now < late_night_start,
        # weil late_night_start am Folgetag liegt und das obere `if`-Fenster
        # diesen Bereich morgen sauber als LATE_NIGHT abdeckt).
        current_idx = 6  # EARLY_NIGHT index in chronological
        for idx in range(len(chronological) - 1):
            _, start = chronological[idx]
            _, next_start = chronological[idx + 1]
            if start <= now < next_start:
                current_idx = idx
                break
        current_phase, current_phase_started_at = chronological[current_idx]
        next_phase, next_phase_at = chronological[current_idx + 1]

    # Master Phase + Übergang
    current_master = DETAIL_TO_MASTER[current_phase]
    next_master = DETAIL_TO_MASTER[next_phase]
    next_master_phase: MasterPhase | None
    next_master_phase_at: datetime | None
    if current_master == next_master:
        next_master_phase = None
        next_master_phase_at = None
    else:
        next_master_phase = next_master
        next_master_phase_at = next_phase_at

    # Attribut-Dicts (HH:MM:SS-Strings laut LH §13).
    phase_starts = {
        phase.slug: start.time().strftime("%H:%M:%S")
        for phase, start in chronological
    }
    master_phase_starts = {
        MasterPhase.MORNING.slug: morning_fix.time().strftime("%H:%M:%S"),
        MasterPhase.MIDDAY.slug: midday_start.time().strftime("%H:%M:%S"),
        MasterPhase.EVENING.slug: evening_start.time().strftime("%H:%M:%S"),
        MasterPhase.NIGHT.slug: night_fix.time().strftime("%H:%M:%S"),
    }

    minutes_until = int((next_phase_at - now).total_seconds() // 60)

    sf = seasonal_factor(_doy(now.date()))
    soff_min = seasonal_offset_seconds(_doy(now.date())) / 60.0

    return DayStateResult(
        detail_phase=current_phase,
        master_phase=current_master,
        phase_starts=phase_starts,
        master_phase_starts=master_phase_starts,
        current_phase_started_at=current_phase_started_at,
        next_phase=next_phase,
        next_phase_at=next_phase_at,
        minutes_until_next_phase=minutes_until,
        next_master_phase=next_master_phase,
        next_master_phase_at=next_master_phase_at,
        solar_noon_at=solar_noon_resolved,
        solar_noon_fallback_active=fallback_active,
        seasonal_factor=sf,
        seasonal_offset_minutes=soff_min,
        morning_fix_at=morning_fix,
        night_fix_at=night_fix,
        midday_start_at=midday_start,
        evening_start_at=evening_start,
        late_morning_start_at=late_morning_start,
        late_evening_start_at=late_evening_start,
        late_night_start_at=late_night_start,
        month_morning_split=MORNING_SPLIT_BY_MONTH[month] or 0.0,
        month_evening_split=EVENING_SPLIT_BY_MONTH[month] or 0.0,
    )
