"""Reine Logik für Presence State (Lastenheft Context State v1.1).

Keine HA-Imports. Alle Funktionen sind deterministisch über ihre Inputs
parametrisiert und in pytest testbar.

Was hier lebt:
- Home-Candidate-Berechnung (R-PS-01..03, GPS-Hierarchie + WLAN-Halte)
- Heimband mit zustandsabhängiger Hysterese (R-PS-11)
- bei_eltern-Auswertung (R-PS-05)
- Haushaltsanwesenheit (R-PS-06)
- Presence-Personal-Komposition

Was im Coordinator lebt (weil Timer + Side-Effects):
- Home-Gate-Stabilisierung (R-PS-04, 60s/150s asymmetrische Delays)
- Transition-Kontext (4.4, 120s Hold)
- Preheat-Auslösung und -Ende (R-PS-07..10, 1200s Hold)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .const import (
    FRESHNESS_ICLOUD_S,
    FRESHNESS_MOBILE_S,
    FRESHNESS_WLAN_S,
    Band,
    PresenceHousehold,
    PresencePersonal,
)


# ─────────────────────────────────────────────────────────────────────────────
# DATEN-STRUKTUREN
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TrackerSnapshot:
    """State + last_updated eines einzelnen Trackers."""

    is_home: bool | None  # True=home, False=not_home, None=unavailable/unknown
    last_updated: datetime | None


@dataclass(frozen=True)
class PresenceInputs:
    """Snapshot aller Inputs zum Auswertungszeitpunkt."""

    icloud: TrackerSnapshot
    mobile: TrackerSnapshot
    wlan_benni: TrackerSnapshot
    wlan_eltern: tuple[TrackerSnapshot, ...]
    distance_m: float | None
    direction: str | None


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _is_fresh(ts: datetime | None, now: datetime, freshness_s: int) -> bool:
    if ts is None:
        return False
    return (now - ts) <= timedelta(seconds=freshness_s)


# ─────────────────────────────────────────────────────────────────────────────
# HOME-CANDIDATE — R-PS-01..03
# ─────────────────────────────────────────────────────────────────────────────


def compute_home_candidate(
    inputs: PresenceInputs,
    now: datetime,
    last_candidate: bool,
) -> tuple[bool, str]:
    """LH R-PS-01 bis R-PS-03.

    Priority:
    1. iCloud3 frisch (<900s) + meldet home → candidate=true (R-PS-01)
    2. iCloud3 frisch not_home + Mobile frisch (<900s) + home → R-PS-02
    3. last_candidate war true + WLAN frisch (<600s) + home → halten (R-PS-03)
    4. Alle Tracker stale → letzten Zustand halten (LH §9)
    5. Sonst → false

    Returns:
        (is_candidate, reason) — reason für Tracing/Debug
    """
    icloud = inputs.icloud
    mobile = inputs.mobile
    wlan = inputs.wlan_benni

    icloud_fresh = _is_fresh(icloud.last_updated, now, FRESHNESS_ICLOUD_S)
    mobile_fresh = _is_fresh(mobile.last_updated, now, FRESHNESS_MOBILE_S)
    wlan_fresh = _is_fresh(wlan.last_updated, now, FRESHNESS_WLAN_S)

    # R-PS-01: iCloud3 primär
    if icloud_fresh and icloud.is_home is True:
        return True, "icloud_home"

    # R-PS-02: Mobile als Stütze, nur wenn iCloud frisch und not_home
    if icloud_fresh and icloud.is_home is False:
        if mobile_fresh and mobile.is_home is True:
            return True, "mobile_home"

    # R-PS-03: WLAN als Halte-Signal — darf nur halten, nicht neu setzen
    if last_candidate and wlan_fresh and wlan.is_home is True:
        return True, "wlan_hold"

    # Alle stale → letzten Zustand halten (LH §9)
    if not icloud_fresh and not mobile_fresh and not wlan_fresh:
        return last_candidate, "all_stale"

    return False, "no_home_signal"


# ─────────────────────────────────────────────────────────────────────────────
# HEIMBAND mit asymmetrischer Hysterese — R-PS-11
# ─────────────────────────────────────────────────────────────────────────────


def _band_from_distance(
    distance: float, home_r: int, near_r: int, preheat_r: int
) -> Band:
    """Naive Band-Zuordnung ohne Hysterese."""
    if distance <= home_r:
        return Band.HOME
    if distance <= near_r:
        return Band.NEAR
    if distance <= preheat_r:
        return Band.PREHEAT
    return Band.FAR


def compute_band(
    distance_m: float | None,
    last_band: Band | None,
    home_radius_m: int,
    near_radius_m: int,
    preheat_radius_m: int,
    hysteresis_m: int,
) -> Band:
    """LH R-PS-11: Bandwechsel asymmetrisch.

    Wechsel in größeres Band braucht `> schwelle + hysterese`.
    Wechsel zurück (kleineres Band) ist sofort, ohne Hysterese.

    Bei distance=None: last_band halten (LH §9 Tracker-Fallback).
    Bei last_band=None (Initial): naive Zuordnung.
    """
    if distance_m is None:
        return last_band or Band.FAR  # initial-fallback

    if last_band is None:
        return _band_from_distance(distance_m, home_radius_m, near_radius_m, preheat_radius_m)

    naive = _band_from_distance(distance_m, home_radius_m, near_radius_m, preheat_radius_m)

    if last_band is Band.HOME:
        # Raus aus home nur wenn deutlich raus
        if distance_m > home_radius_m + hysteresis_m:
            return naive
        return Band.HOME

    if last_band is Band.NEAR:
        # Zurück zu home: sofort
        if distance_m <= home_radius_m:
            return Band.HOME
        # Weiter raus: braucht hysterese
        if distance_m > near_radius_m + hysteresis_m:
            return naive
        return Band.NEAR

    if last_band is Band.PREHEAT:
        if distance_m <= near_radius_m:
            return _band_from_distance(distance_m, home_radius_m, near_radius_m, preheat_radius_m)
        if distance_m > preheat_radius_m + hysteresis_m:
            return Band.FAR
        return Band.PREHEAT

    # last_band is Band.FAR
    if distance_m <= preheat_radius_m:
        return _band_from_distance(distance_m, home_radius_m, near_radius_m, preheat_radius_m)
    return Band.FAR


# ─────────────────────────────────────────────────────────────────────────────
# BEI_ELTERN — R-PS-05
# ─────────────────────────────────────────────────────────────────────────────


def is_bei_eltern(
    band: Band,
    wlan_benni: TrackerSnapshot,
    now: datetime,
) -> bool:
    """LH R-PS-05: Im GPS-Heimbereich UND WLAN-Benni meldet frisch not_home.

    Im Heimbereich = band in {home, near}.

    WLAN-Freshness ist Pflicht — kurzer Router-Dropout darf nicht fälschlich
    bei_eltern auslösen (LH §9).
    """
    if band not in (Band.HOME, Band.NEAR):
        return False
    if not _is_fresh(wlan_benni.last_updated, now, FRESHNESS_WLAN_S):
        return False
    return wlan_benni.is_home is False


# ─────────────────────────────────────────────────────────────────────────────
# PRESENCE_PERSONAL — Komposition
# ─────────────────────────────────────────────────────────────────────────────


def compute_presence_personal(
    home_gate: bool,
    bei_eltern: bool,
) -> PresencePersonal:
    """LH §4.2: bei_eltern hat Vorrang vor home_gate.

    Begründung: Wenn Benni physisch bei den Eltern ist (20m entfernt), kann
    sein GPS noch im Home-Bereich sein und damit home_candidate true setzen.
    Der eigene WLAN-Status ist das entscheidende Diskriminator-Signal.
    """
    if bei_eltern:
        return PresencePersonal.BEI_ELTERN
    if home_gate:
        return PresencePersonal.ZUHAUSE
    return PresencePersonal.ABWESEND


# ─────────────────────────────────────────────────────────────────────────────
# PRESENCE_HOUSEHOLD — R-PS-06
# ─────────────────────────────────────────────────────────────────────────────


def compute_household(
    personal: PresencePersonal,
    wlan_eltern: tuple[TrackerSnapshot, ...],
) -> PresenceHousehold:
    """LH §4.3: leer wenn Benni nicht in der Wohnung UND niemand sonst da.

    Achtung Semantik: `bei_eltern` heißt Benni ist nebenan bei seinen Eltern
    — also physisch NICHT in seiner Wohnung. Für die Haushaltsanwesenheit
    zählt das wie `abwesend`: Eltern müssen separat geprüft werden, ob sie
    in BENNIs Heimnetz sind.
    """
    if personal is PresencePersonal.ZUHAUSE:
        return PresenceHousehold.NICHT_LEER
    for tracker in wlan_eltern:
        if tracker.is_home is True:
            return PresenceHousehold.NICHT_LEER
    return PresenceHousehold.LEER
