"""Unit-Tests für benni_core_presence_state.logic.

Deckt R-PS-01..03 (Home-Candidate), R-PS-05 (bei_eltern), R-PS-06 (Household),
R-PS-11 (Band mit Hysterese), §4.2 (Personal-Komposition) ab.

Timer-basierte Regeln (R-PS-04 Home-Gate, R-PS-07..10 Preheat, Transition)
sind im Coordinator und werden dort separat getestet.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcps_const as C
import bcps_logic as L


TZ = timezone(timedelta(hours=2))
NOW = datetime(2026, 5, 26, 14, 0, tzinfo=TZ)


def _tracker(is_home: bool | None, age_seconds: int | None = 60) -> "L.TrackerSnapshot":
    last = None if age_seconds is None else NOW - timedelta(seconds=age_seconds)
    return L.TrackerSnapshot(is_home=is_home, last_updated=last)


def _inputs(
    icloud: "L.TrackerSnapshot | None" = None,
    mobile: "L.TrackerSnapshot | None" = None,
    wlan_benni: "L.TrackerSnapshot | None" = None,
    wlan_eltern: tuple = (),
    distance_m: float | None = 100,
    direction: str | None = "stationary",
) -> "L.PresenceInputs":
    return L.PresenceInputs(
        icloud=icloud or _tracker(None, None),
        mobile=mobile or _tracker(None, None),
        wlan_benni=wlan_benni or _tracker(None, None),
        wlan_eltern=wlan_eltern,
        distance_m=distance_m,
        direction=direction,
    )


# ─────────────────────────────────────────────────────────────────────────────
# R-PS-01: iCloud3 primär
# ─────────────────────────────────────────────────────────────────────────────


def test_icloud_fresh_home_yields_candidate():
    inp = _inputs(icloud=_tracker(True, 100))
    is_cand, reason = L.compute_home_candidate(inp, NOW, last_candidate=False)
    assert is_cand is True
    assert reason == "icloud_home"


def test_icloud_stale_home_does_not_yield_candidate():
    inp = _inputs(icloud=_tracker(True, age_seconds=1000))  # > 900s
    is_cand, _ = L.compute_home_candidate(inp, NOW, last_candidate=False)
    assert is_cand is False


# ─────────────────────────────────────────────────────────────────────────────
# R-PS-02: Mobile als Stütze
# ─────────────────────────────────────────────────────────────────────────────


def test_mobile_home_picked_when_icloud_says_not_home():
    inp = _inputs(
        icloud=_tracker(False, 100),
        mobile=_tracker(True, 100),
    )
    is_cand, reason = L.compute_home_candidate(inp, NOW, last_candidate=False)
    assert is_cand is True
    assert reason == "mobile_home"


def test_mobile_ignored_when_icloud_fresh_home():
    # iCloud3 primär — Mobile-Wert irrelevant wenn iCloud schon home sagt
    inp = _inputs(
        icloud=_tracker(True, 100),
        mobile=_tracker(False, 100),
    )
    is_cand, reason = L.compute_home_candidate(inp, NOW, last_candidate=False)
    assert is_cand is True
    assert reason == "icloud_home"


def test_mobile_ignored_when_icloud_stale():
    # LH §2.2 R-PS-02: explizit "iCloud3 frisch not_home" als Vorbedingung
    inp = _inputs(
        icloud=_tracker(True, 1000),  # stale
        mobile=_tracker(True, 100),
    )
    is_cand, _ = L.compute_home_candidate(inp, NOW, last_candidate=False)
    assert is_cand is False


# ─────────────────────────────────────────────────────────────────────────────
# R-PS-03: WLAN als Halte-Signal
# ─────────────────────────────────────────────────────────────────────────────


def test_wlan_holds_candidate_when_previously_home():
    # GPS sagt nichts, WLAN sagt home → halten weil last_candidate=true
    inp = _inputs(wlan_benni=_tracker(True, 100))
    is_cand, reason = L.compute_home_candidate(inp, NOW, last_candidate=True)
    assert is_cand is True
    assert reason == "wlan_hold"


def test_wlan_alone_does_not_create_new_candidate():
    # KRITISCHE LH-Regel R-PS-03: WLAN allein darf KEIN neues home auslösen
    inp = _inputs(wlan_benni=_tracker(True, 100))
    is_cand, _ = L.compute_home_candidate(inp, NOW, last_candidate=False)
    assert is_cand is False


def test_all_stale_holds_last_candidate():
    # LH §9: alle Tracker stale → halten
    inp = _inputs(
        icloud=_tracker(True, 2000),  # stale
        wlan_benni=_tracker(True, 2000),  # stale
    )
    is_cand_was_home, reason = L.compute_home_candidate(inp, NOW, last_candidate=True)
    assert is_cand_was_home is True
    assert reason == "all_stale"

    is_cand_was_away, reason2 = L.compute_home_candidate(inp, NOW, last_candidate=False)
    assert is_cand_was_away is False
    assert reason2 == "all_stale"


# ─────────────────────────────────────────────────────────────────────────────
# R-PS-11: Band mit Hysterese
# ─────────────────────────────────────────────────────────────────────────────


def test_band_initial_zuordnung_ohne_letzten_state():
    # Initial: keine Hysterese-Berücksichtigung
    assert L.compute_band(100, None, 150, 250, 1500, 100) is C.Band.HOME
    assert L.compute_band(200, None, 150, 250, 1500, 100) is C.Band.NEAR
    assert L.compute_band(800, None, 150, 250, 1500, 100) is C.Band.PREHEAT
    assert L.compute_band(2000, None, 150, 250, 1500, 100) is C.Band.FAR


def test_band_hysterese_hold_home_short_excursion():
    # last_band=home, distance=200m liegt > home_radius=150 aber < home+hyst=250
    # → halten als home
    assert L.compute_band(200, C.Band.HOME, 150, 250, 1500, 100) is C.Band.HOME


def test_band_release_home_skips_to_preheat_at_default_radii():
    # SUBTILITÄT: Mit den Defaults aus LH §6 (home_radius=150,
    # near_radius=250, hysteresis=100) ist die home-Hysterese-Schwelle
    # (150+100=250m) GLEICH der near-Grenze. Folge: NEAR ist vom HOME
    # aus per Hysterese nicht direkt erreichbar — man springt zu PREHEAT.
    # NEAR wird nur beim Annähern von außen (PREHEAT→NEAR) durchlaufen.
    # LH-konform (NEAR ist Pufferzone "von außen"), aber gut dokumentiert.
    assert L.compute_band(260, C.Band.HOME, 150, 250, 1500, 100) is C.Band.PREHEAT


def test_band_can_reach_near_from_preheat_when_approaching():
    # preheat → near beim Annähern (sofort, ohne Hysterese)
    assert L.compute_band(200, C.Band.PREHEAT, 150, 250, 1500, 100) is C.Band.NEAR


def test_band_home_to_near_reachable_with_smaller_hysteresis():
    # Wenn home_radius + hysteresis < near_radius, ist NEAR vom HOME aus
    # erreichbar. Beispiel: home=100, hyst=50, near=250 → home+hyst=150,
    # also distance=200 wechselt zu NEAR.
    assert L.compute_band(200, C.Band.HOME, 100, 250, 1500, 50) is C.Band.NEAR


def test_band_return_to_home_is_immediate():
    # last_band=near, distance=120 < home_radius=150 → sofort home
    assert L.compute_band(120, C.Band.NEAR, 150, 250, 1500, 100) is C.Band.HOME


def test_band_unknown_distance_holds_last():
    # LH §9: distance None → last halten
    assert L.compute_band(None, C.Band.NEAR, 150, 250, 1500, 100) is C.Band.NEAR
    assert L.compute_band(None, C.Band.HOME, 150, 250, 1500, 100) is C.Band.HOME


def test_band_far_to_preheat_immediate():
    # Rückkehr ohne Hysterese
    assert L.compute_band(1400, C.Band.FAR, 150, 250, 1500, 100) is C.Band.PREHEAT


def test_band_preheat_to_far_needs_hysteresis():
    # 1550 < preheat+hyst=1600 → halten
    assert L.compute_band(1550, C.Band.PREHEAT, 150, 250, 1500, 100) is C.Band.PREHEAT
    # 1700 > 1600 → wechseln
    assert L.compute_band(1700, C.Band.PREHEAT, 150, 250, 1500, 100) is C.Band.FAR


# ─────────────────────────────────────────────────────────────────────────────
# R-PS-05: bei_eltern
# ─────────────────────────────────────────────────────────────────────────────


def test_bei_eltern_band_home_wlan_not_home_fresh():
    # Band home + WLAN frisch not_home → bei_eltern
    assert L.is_bei_eltern(C.Band.HOME, _tracker(False, 60), NOW) is True


def test_bei_eltern_band_near_also_qualifies():
    assert L.is_bei_eltern(C.Band.NEAR, _tracker(False, 60), NOW) is True


def test_bei_eltern_blocked_at_preheat_band():
    # Außerhalb GPS-Heimbereich kein bei_eltern
    assert L.is_bei_eltern(C.Band.PREHEAT, _tracker(False, 60), NOW) is False


def test_bei_eltern_blocked_when_wlan_stale():
    # LH §9: kurzer Router-Dropout (WLAN stale) darf nicht fälschlich
    # bei_eltern auslösen
    assert L.is_bei_eltern(C.Band.HOME, _tracker(False, age_seconds=700), NOW) is False


def test_bei_eltern_blocked_when_wlan_home():
    # WLAN sagt home → Benni ist in eigener Wohnung, nicht bei Eltern
    assert L.is_bei_eltern(C.Band.HOME, _tracker(True, 60), NOW) is False


def test_bei_eltern_blocked_when_wlan_unknown():
    # WLAN unknown ist nicht "not_home" — konservativ false
    assert L.is_bei_eltern(C.Band.HOME, _tracker(None, 60), NOW) is False


# ─────────────────────────────────────────────────────────────────────────────
# Presence-Personal-Komposition
# ─────────────────────────────────────────────────────────────────────────────


def test_presence_personal_bei_eltern_overrides_home_gate():
    # Konflikt-Fall: GPS sagt home (home_gate=True) aber WLAN-Benni sagt
    # not_home (bei_eltern=True). bei_eltern muss gewinnen.
    assert L.compute_presence_personal(home_gate=True, bei_eltern=True) is C.PresencePersonal.BEI_ELTERN


def test_presence_personal_zuhause_when_home_gate_and_not_bei_eltern():
    assert L.compute_presence_personal(home_gate=True, bei_eltern=False) is C.PresencePersonal.ZUHAUSE


def test_presence_personal_abwesend_when_neither():
    assert L.compute_presence_personal(home_gate=False, bei_eltern=False) is C.PresencePersonal.ABWESEND


# ─────────────────────────────────────────────────────────────────────────────
# R-PS-06: Household
# ─────────────────────────────────────────────────────────────────────────────


def test_household_nicht_leer_when_benni_zuhause():
    assert L.compute_household(C.PresencePersonal.ZUHAUSE, ()) is C.PresenceHousehold.NICHT_LEER


def test_household_nicht_leer_when_eltern_da():
    assert L.compute_household(
        C.PresencePersonal.ABWESEND,
        wlan_eltern=(_tracker(True, 100),),
    ) is C.PresenceHousehold.NICHT_LEER


def test_household_leer_when_all_away():
    assert L.compute_household(
        C.PresencePersonal.ABWESEND,
        wlan_eltern=(_tracker(False, 100), _tracker(False, 100)),
    ) is C.PresenceHousehold.LEER


def test_household_leer_when_bei_eltern_and_no_eltern_in_wohnung():
    # Benni bei Eltern (nebenan) UND keine Eltern in BENNIs Wohnung → leer
    assert L.compute_household(
        C.PresencePersonal.BEI_ELTERN,
        wlan_eltern=(_tracker(False, 100),),
    ) is C.PresenceHousehold.LEER


def test_household_nicht_leer_when_bei_eltern_but_eltern_in_wohnung():
    # Benni bei Eltern + Elternteil ist in BENNIs Heimnetz → nicht_leer
    assert L.compute_household(
        C.PresencePersonal.BEI_ELTERN,
        wlan_eltern=(_tracker(True, 100),),
    ) is C.PresenceHousehold.NICHT_LEER


def test_household_unknown_eltern_tracker_treated_as_away():
    # Eltern-Tracker is_home=None → nicht als zuhause werten (konservativ)
    assert L.compute_household(
        C.PresencePersonal.ABWESEND,
        wlan_eltern=(_tracker(None, 100),),
    ) is C.PresenceHousehold.LEER
